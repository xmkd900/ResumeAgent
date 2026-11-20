"""单轮判卷 v3：逐要点语义判定 + 代码聚合。

设计原则（ADR-006）：

- **语义归模型，算术归代码。** 期望要点编号 P1..Pn，模型逐条给
  `covered / partial / missing` 与原文引用；代码按编号聚合，不做任何
  "要点文本 vs 回答文本"的字符串匹配——那正是"换个说法就判没答到"的根因。
- **代码只做机械校验。** 引用能否在回答里定位（`locate_quote`）是可验证的，
  定位不到只降级为 partial，不直接判缺失。
- **不惩罚口头语。** "好像是/大概/我记得"是正常说话方式，不再触发任何上限；
  清晰度由模型整体判断，并且明确要求口头语不扣分。
- **上限只留给真正硬的情况**：一条都没答到、明确承认不会、回答过短、前后矛盾。
"""

import logging

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.llm.json import extract_json_object
from app.schemas.interview import JudgeEvidence, JudgementOut
from app.services.text_match import locate_quote

logger = logging.getLogger(__name__)

DIMENSION_MAX: dict[str, int] = {
    "coverage": 25,
    "specificity": 25,
    "reasoning": 25,
    "authenticity": 15,
    "clarity": 10,
}

DIMENSION_LABELS: dict[str, str] = {
    "coverage": "要点覆盖",
    "specificity": "具体程度",
    "reasoning": "推理深度",
    "authenticity": "依据充分",
    "clarity": "表达结构",
}

VERDICT_GOOD = 80
VERDICT_PARTIAL = 60

# 引用定位阈值：达到即视为"原文有依据"（只做防伪造，不做语义判断）
QUOTE_GROUNDED = 0.9

JUDGE_SYSTEM_PROMPT = """你是资深技术面试官，负责给候选人的一段回答打分。
你的任务不是"对关键词"，而是判断：这段回答有没有**实质答到**每一条期望要点。

## 一、逐条判定（最重要）
用户会给出编号后的期望要点（P1、P2…）。对每一条给一个 status：

- covered：实质答到了。**允许同义表达、换措辞、举例、反向说明、用自己的话解释**；
  只要含义等价就算 covered，不能因为用词和要点不一样就判 partial/missing。
- partial：说到了相关方向，但缺关键限定、机制或结果（例如只说了"用什么"，没说"为什么/怎么验证"）。
- missing：完全没有实质性提及。

判定依据是**含义**，不是字面。示例：
期望要点 P1：通过日志记录消费耗时并聚合统计
回答："我把 sendTimestamp 塞进消息体，消费时算差值打到日志里，再用 grep/awk 看分布"
→ covered（换了说法，但日志 + 统计都在）
回答："我主要看 RabbitMQ 管理后台的 Ready 数"
→ missing（没有日志聚合）

反过来，只是蹦出一个名词也不算 covered：
回答："日志这块我知道，可以用 ELK"
→ partial（提了方向，没有自己的做法）

## 二、引用要求
- status 为 covered / partial 时，必须给 quote：从回答里**逐字**摘 10-40 字。
- quote 是"该要点在回答中的依据"，不是复述题目；抄不出就说明这条不该判 covered。
- 系统会校验 quote 能否在回答中定位；定位不到会自动降级，所以不要编造引用。

## 三、四个维度（各自打点，不要给总分）
- specificity 具体性（0-25）：有没有可核对细节——你的角色、数量级、时间、工具版本、报错现象。
  20-25 多个可核对细节；12-19 部分细节；5-11 只有流程；0-4 全是套话。
- reasoning 推理深度（0-25）：有没有讲清因果、取舍、边界、怎么验证。
- authenticity 依据充分（0-15）：结论有没有依据——项目事实、数据、原理推导都算；
  15 依据充分且能指出来源，8-14 有依据但不够具体，0-7 空口断言。
  **概念题用原理解释清楚同样可以拿高分，不要求一手经历。**
- clarity 表达结构（0-10）：结论先行、分层清楚、无自相矛盾、答非所问。
  **口语化不扣分**："好像/大概/我记得/其实"这类词是正常说话方式，
  只要内容可核对就不影响 clarity；只有逻辑跳跃、前后矛盾、跑题才扣。

## 四、其他信号
- depth：recall 只能复述名词 / understood 能讲清原理 / applied 有动手细节 / reflective 能反思局限。
- contradiction：与历史或简历冲突、或本轮自相矛盾时填 minor/major，否则 none。
- declared_unknown：候选人明确说"没做过/不知道"时填 true；此时如实低分，但
  probe_needed 填 false（不要追着问）。
- probe：把这段回答里**最经不起追问的一点**写进 probe_target；回答扎实时 probe_needed=false。
- feedback：不超过 100 字，必须点名具体内容（引用他说过的词），先判断后依据。

只输出 JSON，不要 markdown：
{
  "points": [
    {"id": 1, "status": "covered | partial | missing", "quote": "回答原文", "note": "一句话说明"}
  ],
  "specificity": 0,
  "reasoning": 0,
  "authenticity": 0,
  "clarity": 0,
  "depth": "recall | understood | applied | reflective",
  "contradiction": "none | minor | major",
  "declared_unknown": false,
  "probe_needed": true,
  "probe_target": "",
  "feedback": ""
}"""


class JudgeError(Exception):
    """判卷服务异常。

    Attributes:
        status_code: HTTP状态码，默认502
    """

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class PointVerdict(BaseModel):
    """单条期望要点的判定。id 对应输入里的 P1..Pn。"""

    id: int
    status: str = "missing"
    quote: str = ""
    note: str = ""


class JudgeOutput(BaseModel):
    """模型原始输出：逐条判定 + 维度分点，没有总分。"""

    points: list[PointVerdict] = Field(default_factory=list)
    specificity: int = 0
    reasoning: int = 0
    authenticity: int = 0
    clarity: int = 0
    depth: str = "recall"
    contradiction: str = "none"
    declared_unknown: bool = False
    probe_needed: bool = False
    probe_target: str = ""
    feedback: str = ""


def _clamp(value: int, upper: int) -> int:
    return max(0, min(int(value or 0), upper))


def _status_of(raw: str) -> str:
    value = (raw or "").strip().lower()
    return value if value in {"covered", "partial", "missing"} else "missing"


def score_judgement(
    *,
    output: JudgeOutput,
    expected_points: list[str],
    answer: str,
) -> JudgementOut:
    """把逐条判定折算成 0-100。

    纯函数，不调用模型：同样的输入永远得到同样的分数。
    覆盖分 = (covered + 0.5 × partial) / 要点数，部分覆盖不再被当成"没答"。
    """
    points = [str(item).strip() for item in expected_points if str(item).strip()]
    text = (answer or "").strip()
    verdicts = {
        item.id: item for item in output.points if 1 <= item.id <= max(1, len(points))
    }

    covered: list[str] = []
    partial: list[str] = []
    missing: list[str] = []
    rows: list[dict] = []
    evidence: list[JudgeEvidence] = []
    unverified = 0

    for index, point in enumerate(points, start=1):
        verdict = verdicts.get(index)
        status = _status_of(verdict.status) if verdict else "missing"
        quote = (verdict.quote or "").strip() if verdict else ""
        note = (verdict.note or "").strip()[:120] if verdict else ""
        verified = False

        if status in {"covered", "partial"}:
            if not quote:
                # 没有引用就没有依据：降级而不是判死，避免把"模型漏抄"当成"没答"
                status = "partial"
                note = note or "未提供原文引用"
            else:
                match = locate_quote(quote, text)
                verified = match.score >= QUOTE_GROUNDED
                if verified:
                    quote = match.text  # 回填原文片段，保证引用真实
                elif status == "covered":
                    # 引用定位不到：不能算扎实命中，但也不判缺失
                    status = "partial"
                    unverified += 1
                    note = note or "引用未能在回答中定位"

        if status == "covered":
            covered.append(point)
        elif status == "partial":
            partial.append(point)
        else:
            missing.append(point)
        if quote and status != "missing":
            evidence.append(JudgeEvidence(point=point, quote=quote))
        rows.append(
            {
                "id": index,
                "point": point,
                "status": status,
                "quote": quote,
                "verified": verified,
                "note": note,
            }
        )

    # 覆盖分：部分覆盖给一半，不再把"换了说法"判成零
    if points:
        ratio = (len(covered) + 0.5 * len(partial)) / len(points)
        coverage = round(DIMENSION_MAX["coverage"] * (0.4 + 0.6 * ratio)) if ratio else 0
    else:
        coverage = 25 if covered else 15 if partial else 0

    specificity = _clamp(output.specificity, 25)
    reasoning = _clamp(output.reasoning, 25)
    authenticity = _clamp(output.authenticity, 15)
    clarity = _clamp(output.clarity, 10)

    score = max(0, min(100, coverage + specificity + reasoning + authenticity + clarity))
    capped_by = ""

    def cap(limit: int, reason: str) -> None:
        nonlocal score, capped_by
        if score > limit:
            score = limit
            capped_by = capped_by or reason

    # 上限只留给真正硬的情况；不再根据口头语、复述深度等软信号扣分
    if not covered and not partial:
        cap(35, "所有要点缺失")
    # 有判定但一条引用都核实不了：内容无法验证，不给高分（不因此判成缺失）
    if (covered or partial) and not any(row["verified"] for row in rows):
        cap(70, "引用无法核实")
    if output.declared_unknown:
        cap(36, "承认不会")
    if output.contradiction == "major":
        cap(40, "前后矛盾")
    elif output.contradiction == "minor":
        cap(74, "细节前后不一致")
    if len(text) < 15:
        cap(40, "回答过短")

    verdict = (
        "good" if score >= VERDICT_GOOD
        else "partial" if score >= VERDICT_PARTIAL
        else "bad"
    )
    probe_target = (output.probe_target or "").strip()[:160]
    probe_needed = (
        bool(output.probe_needed) and not output.declared_unknown and len(text) >= 10
    )

    return JudgementOut(
        verdict=verdict,
        score=score,
        hit_points=covered[:6],
        partial_points=partial[:6],
        missing_points=missing[:6],
        followup_hint=probe_target if probe_needed else "",
        feedback=(output.feedback or "").strip()[:200],
        point_results=rows,
        dimensions={
            "coverage": coverage,
            "specificity": specificity,
            "reasoning": reasoning,
            "authenticity": authenticity,
            "clarity": clarity,
        },
        evidence=evidence[:6],
        depth=output.depth
        if output.depth in {"recall", "understood", "applied", "reflective"}
        else "",
        probe_needed=probe_needed,
        probe_target=probe_target if probe_needed else "",
        contradiction=(
            output.contradiction
            if output.contradiction in {"none", "minor", "major"}
            else "none"
        ),
        declared_unknown=bool(output.declared_unknown),
        capped_by=capped_by,
    )


# --------------------------------------------------------------------------- #
# 模型调用
# --------------------------------------------------------------------------- #
def _render_points(points: list[str]) -> str:
    return "\n".join(f"P{index}. {point}" for index, point in enumerate(points, start=1))


def _render_history(history: list[dict] | None) -> str:
    lines: list[str] = []
    for item in (history or [])[-3:]:
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question:
            continue
        lines.append(f"问: {question[:160]}\n答: {answer[:220] or '（未答）'}")
    return "\n".join(lines) or "（这是第一轮有效问答）"


def _render_claim(claim: dict | None) -> str:
    if not claim:
        return "（本轮不针对简历要点）"
    tags = "、".join(claim.get("tags") or []) or "无"
    return (
        f"{claim.get('title')} | 技术: {tags} | 简历原文: "
        f"{str(claim.get('evidence') or '')[:160]}"
    )


def judge_answer(
    *,
    question: str,
    expected_points: list[str] | None,
    rubric: dict | None,
    answer: str,
    position: str = "",
    claim: dict | None = None,
    history: list[dict] | None = None,
    depth: int = 0,
) -> JudgementOut:
    """对一轮回答判卷；格式错误重试一次，失败抛 JudgeError。"""
    if not (settings.LLM_API_KEY or "").strip():
        raise JudgeError("未配置 LLM_API_KEY，无法调用判卷模型", status_code=503)

    points = [str(item).strip() for item in (expected_points or []) if str(item).strip()]
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"<position>{position or '未指定'}</position>\n"
                f"<question>\n{question}\n</question>\n"
                f"<expected_points>\n{_render_points(points)}\n</expected_points>\n"
                f"<rubric>\n{rubric or {}}</rubric>\n"
                f"<resume_claim>\n{_render_claim(claim)}\n</resume_claim>\n"
                f"<history>\n{_render_history(history)}\n</history>\n"
                f"<followup_depth>{depth}</followup_depth>\n"
                f"<answer>\n{answer[:3000]}\n</answer>"
            ),
        },
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        content = ""
        try:
            response = chat(messages, max_tokens=1400, temperature=0.0)
            content = response.content
            output = JudgeOutput.model_validate(extract_json_object(content))
            return score_judgement(output=output, expected_points=points, answer=answer)
        except (ValueError, TypeError, ValidationError) as exc:
            last_error = exc
            logger.warning("judge output invalid (attempt %s): %s", attempt + 1, exc)
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": content[:2000] or "{}"},
                    {
                        "role": "user",
                        "content": (
                            f"上一次输出不符合要求：{str(exc)[:300]}。"
                            "请只返回 points（每条含 id/status/quote/note）、"
                            "specificity/reasoning/authenticity/clarity/depth/"
                            "contradiction/declared_unknown/probe_needed/"
                            "probe_target/feedback 的 JSON；points 的 id 必须覆盖 P1..Pn。"
                        ),
                    },
                ]
                continue
        except LLMError as exc:
            raise JudgeError(str(exc), status_code=exc.status_code) from exc
        except Exception as exc:
            logger.exception("judge failed")
            raise JudgeError("判卷服务暂时不可用，请稍后重试", status_code=502) from exc

    raise JudgeError("判卷结果格式不符合要求，已重试仍失败", status_code=502) from last_error


__all__ = [
    "DIMENSION_LABELS",
    "DIMENSION_MAX",
    "JudgeError",
    "JudgeOutput",
    "PointVerdict",
    "judge_answer",
    "score_judgement",
]
