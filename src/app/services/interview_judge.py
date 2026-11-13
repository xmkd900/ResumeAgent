"""单轮判卷：只做文本判断，不碰数据库、不决定下一题。

v2 口径（与 v1 的差别，见 ARCHITECTURE.md ADR-004）：

1. **先取证，再打分**：每个命中点都要在回答里抄出原文（`quote`），
   抄不出原话的一律不算命中——这一条直接堵住"沾到关键词就给分"。
2. **分维度打点，总分由代码算**：覆盖/具体/推理/自证/结构各自封顶，
   加权求和后落在 0-100。模型不再直接给总分，避免"感觉不错给 88"。
3. **明确的扣分信号做成硬规则**：模糊限定（好像是/记不清）、纯背书、
   只给结论、前后矛盾、答非所问，都会触发上限，而不是指望模型自觉。
4. **"不知道"如实记低分但不挖坑**：承认不会是一种有效信息，
   分数上不去，但反馈语气认可坦诚，面试官也不会追着问。
"""

import logging
import re

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.llm.json import extract_json_object
from app.schemas.interview import JudgeEvidence, JudgementOut

logger = logging.getLogger(__name__)

# 维度分点上限：合计 100。权重顺序 = 面试官真正在意的顺序（内容 > 细节 > 推理 > 自证 > 表达）
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
    "authenticity": "经历自证",
    "clarity": "表达结构",
}

# 模糊限定词：命中越多越像"背了个大概"，这是"很水但沾边"最典型的指纹
HEDGE_MARKERS = (
    "好像是",
    "好像",
    "大概",
    "记不太清",
    "记不清",
    "我记得是",
    "我记得",
    "应该是",
    "应该就是",
    "差不多",
    "可能吧",
    "具体忘了",
    "不太确定",
    "反正是",
    "印象中",
    "似乎",
    "估计",
    "也许",
)

# 诚实承认不会：这类回答分低但不该被"猜"惩罚，也不该被继续拷问
UNKNOWN_MARKERS = (
    "不知道",
    "不太清楚",
    "没做过",
    "没接触过",
    "不了解",
    "不会",
    "没了解过",
)

VERDICT_GOOD = 80
VERDICT_PARTIAL = 60

JUDGE_SYSTEM_PROMPT = """你是资深技术面试官，负责给候选人的一段回答打分。
你的任务不是"找关键词"，而是判断：这段回答能不能证明他**真的做过、真的想过**。

## 第一原则：只认原文证据
- 每一个命中要点，必须从<answer>里**逐字**抄一段原话放进 quote（10-40 字，不要改写、不要概括）。
- evidence.point **必须从 <expected_points> 里原样复制一条**；对不上任何期望要点的证据不要写进来。
- 能对上的要点都要记下来，不要漏；但每条都必须有原文 quote——抄不出原话的宁可不记，也不要脑补。
- 名词对上了但没有任何"我做了什么 / 怎么做的 / 结果怎样"，只能算"知道这个词"，不能算"做过"。

## 五个维度（各自打点，不要给总分）
- specificity 具体性（0-25）：有没有可核对的细节——你的角色、数量级、时间、工具版本、报错现象、谁做的决定。
  20-25 有多个可核对细节；12-19 有部分细节但不完整；5-11 只有流程没有细节；0-4 全是套话。
- reasoning 推理深度（0-25）：有没有讲清因果、取舍、边界、怎么验证。
  20-25 有取舍和验证；12-19 因果清楚但停在"用了就好了"；5-11 只有结论；0-4 逻辑断裂或答非所问。
- authenticity 自证程度（0-15）：15 一手经历（我做的、我踩的坑、我改的）；
  8-14 参与但关键决策是别人做的；0-7 转述、背概念、无法判断是否亲历。
- clarity 表达结构（0-10）：8-10 结论先行、分层清楚、无自相矛盾；
  5-7 能听懂但绕；0-4 前后矛盾、跳跃、答非所问。不评价口音、词藻、语速。
- coverage 由系统按证据计算，你不用填。

## 扣分信号（最容易放水的地方，必须严格执行）
1. 模糊限定：出现"好像是 / 大概 / 记不清 / 应该是 / 差不多 / 可能吧"这类词
   —— 2 处以上，specificity 不得高于 12；3 处以上，authenticity 不得高于 7。
2. 只给结论："加了注解就行了""用了 XX 就好了"——reasoning 不得高于 12。
3. 数字无来源：说了 QPS/耗时/百分比，但说不清怎么测的——specificity 不得高于 15。
4. 前后矛盾：与 <history> 或 <resume_claim> 冲突，或本轮自相矛盾——contradiction 填 minor/major。
5. 空话套话：整段没有第一人称的具体动作——authenticity 不得高于 4。
6. 明确承认"没做过 / 不知道"：declared_unknown=true，如实低分，但 feedback 要认可坦诚，
   probe_needed 填 false（不要再追着问）。

## depth 档位
- recall：只能复述名词或流程
- understood：能解释原理、知道为什么
- applied：有自己动手的具体细节和踩过的坑
- reflective：还能说出局限、失败案例、重做会怎么改

## probe 验真
把这段回答里**最经不起追问的那一点**写进 probe_target（一句话，指向具体表述，不要泛泛而谈）。
只有当回答确实扎实、没有可疑表述时才 probe_needed=false。

## feedback
不超过 100 字，必须点名具体内容（引用他说过的词），先给判断再给依据。
不许写"表现不错""继续加油"这种放之四海皆准的话。

只输出 JSON，不要 markdown，不要解释：
{
  "evidence": [{"point": "从 expected_points 原样复制的一条", "quote": "回答原文片段"}],
  "missing_points": ["没答到的期望要点，只能从 expected_points 里选"],
  "specificity": 0,
  "reasoning": 0,
  "authenticity": 0,
  "clarity": 0,
  "depth": "recall | understood | applied | reflective",
  "hedging": ["回答里实际出现的模糊词"],
  "contradiction": "none | minor | major",
  "declared_unknown": false,
  "probe_needed": true,
  "probe_target": "最该追问的那一点",
  "feedback": "一句话判断 + 依据"
}"""


class JudgeError(Exception):
    """判卷服务异常。

    Attributes:
        status_code: HTTP状态码，默认502
    """

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class JudgeOutput(BaseModel):
    """模型原始判卷输出：只有维度分点，没有总分。"""

    evidence: list[JudgeEvidence] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    specificity: int = 0
    reasoning: int = 0
    authenticity: int = 0
    clarity: int = 0
    depth: str = "recall"
    hedging: list[str] = Field(default_factory=list)
    contradiction: str = "none"
    declared_unknown: bool = False
    probe_needed: bool = False
    probe_target: str = ""
    feedback: str = ""


# --------------------------------------------------------------------------- #
# 打分：全部由代码完成，模型只提供维度分点与证据
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    return re.sub(r"[\s，。？！、,.?!:：；;\"'“”‘’（）()]", "", (text or "")).lower()


def _same_point(left: str, right: str) -> bool:
    """判断两个要点表述是否指向同一件事（容忍改写）。"""
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _clamp(value: int, upper: int) -> int:
    return max(0, min(int(value or 0), upper))


def detect_hedges(text: str) -> list[str]:
    """在原文里数模糊限定词。

    不采信模型自报的词表——模型会把"其实""偶尔"也算进去，那会误伤正常回答。
    这里按原文逐字扫描，长词优先，同一处只记一次。
    """
    found: list[str] = []
    index = 0
    ordered = sorted(HEDGE_MARKERS, key=len, reverse=True)
    while index < len(text):
        matched = next((marker for marker in ordered if text.startswith(marker, index)), None)
        if matched:
            if matched not in found:
                found.append(matched)
            index += len(matched)
        else:
            index += 1
    return found


def score_judgement(
    *,
    output: JudgeOutput,
    expected_points: list[str],
    answer: str,
) -> JudgementOut:
    """把维度分点折算成 0-100，并施加硬性上限。

    纯函数，不调用模型：同样的输入永远得到同样的分数，便于测试与复盘。
    """
    points = [str(item).strip() for item in expected_points if str(item).strip()]
    text = (answer or "").strip()

    # 1) 证据 → 命中要点。没有 quote 的 evidence 直接丢弃
    evidence = [
        JudgeEvidence(point=str(item.point).strip(), quote=str(item.quote).strip())
        for item in output.evidence
        if str(item.quote or "").strip() and str(item.point or "").strip()
    ]
    hits: list[str] = []
    for item in evidence:
        target = next(
            (point for point in points if _same_point(item.point, point)),
            None,
        )
        if target and target not in hits:
            hits.append(target)

    # 2) 覆盖分：只按"有原文依据"的命中算。
    #    命中一半不等于半分不给：答到一部分也要给基础分，
    #    否则"要点没列全"会被具体性、推理各扣一遍，变成三重惩罚。
    if points:
        ratio = min(1.0, len(hits) / len(points))
        if ratio:
            coverage = round(DIMENSION_MAX["coverage"] * (0.4 + 0.6 * ratio))
        else:
            # 有原文、但一条期望要点都没对上：答了些相关内容却没答到点上
            coverage = 10 if evidence else 0
    else:
        coverage = 25 if len(evidence) >= 2 else 15 if evidence else 0

    specificity = _clamp(output.specificity, 25)
    reasoning = _clamp(output.reasoning, 25)
    authenticity = _clamp(output.authenticity, 15)
    clarity = _clamp(output.clarity, 10)

    # 3) 模糊词一律由代码数，不用模型自报的清单
    hedging = detect_hedges(text)

    raw = coverage + specificity + reasoning + authenticity + clarity
    score = max(0, min(100, raw))
    capped_by = ""

    def cap(limit: int, reason: str) -> None:
        nonlocal score, capped_by
        if score > limit:
            score = limit
            capped_by = capped_by or reason

    # 4) 硬规则：宁可在边界上误伤，也不要让"空话"混进 80+
    if not evidence:
        cap(35, "无原文证据")
    if len(hedging) >= 3:
        cap(55, "模糊表述过多")
    elif len(hedging) >= 2 and specificity <= 12:
        cap(58, "模糊且缺细节")
    if authenticity <= 4 and specificity <= 14:
        cap(58, "只有概念没有亲历")
    if reasoning <= 12 and specificity <= 12:
        cap(60, "只有结论没有过程")
    if output.depth == "recall":
        cap(68, "停留在复述")
    if output.contradiction == "major":
        cap(40, "前后矛盾")
    elif output.contradiction == "minor":
        cap(74, "细节前后不一致")
    if output.declared_unknown:
        cap(36, "承认不会")
    if len(text) < 25:
        cap(40, "回答过短")

    # 5) 下限：答到了点子上、只是不够深的回答，不该被判成"零基础"
    if evidence and not output.declared_unknown and score < 38:
        score = 38

    verdict = (
        "good" if score >= VERDICT_GOOD
        else "partial" if score >= VERDICT_PARTIAL
        else "bad"
    )

    # 缺口 = 期望要点里没被证据支撑的部分；没有期望要点时才采信模型标注
    missing = [point for point in points if point not in hits][:6]
    if not points:
        missing = [str(item).strip() for item in output.missing_points if str(item).strip()][:6]

    probe_target = (output.probe_target or "").strip()[:160]
    probe_needed = bool(output.probe_needed) and not output.declared_unknown and len(text) >= 10

    return JudgementOut(
        verdict=verdict,
        score=score,
        hit_points=hits[:6],
        missing_points=missing,
        followup_hint=probe_target if probe_needed else "",
        feedback=(output.feedback or "").strip()[:200],
        dimensions={
            "coverage": coverage,
            "specificity": specificity,
            "reasoning": reasoning,
            "authenticity": authenticity,
            "clarity": clarity,
        },
        evidence=evidence[:6],
        depth=output.depth if output.depth in {"recall", "understood", "applied", "reflective"} else "",
        probe_needed=probe_needed,
        probe_target=probe_target if probe_needed else "",
        hedging=hedging[:6],
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
                f"<expected_points>\n{points}\n</expected_points>\n"
                f"<rubric>\n{rubric or {}}\n</rubric>\n"
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
            response = chat(messages, max_tokens=1200, temperature=0.0)
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
                            "请只返回 evidence/missing_points/specificity/reasoning/"
                            "authenticity/clarity/depth/hedging/contradiction/"
                            "declared_unknown/probe_needed/probe_target/feedback 的 JSON，"
                            "每条 evidence 必须带 answer 里的原文 quote。"
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
    "judge_answer",
    "score_judgement",
]
