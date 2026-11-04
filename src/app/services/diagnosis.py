"""简历诊断服务：LLM 结构化输出，失败即明确报错。

设计约束：
- 不把启发式结果当作“兜底报告”写库；只有显式 LLM_MOCK=true 才用于本地测试；
- 每次调用都要求 JSON，并用 Pydantic 校验；格式错误最多重试一次；
- 鉴权、限流、超时、网络、输出截断分别给出可读错误，不静默降级；
- 报告只在完整校验通过后落库。
"""

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.schemas.resume import DiagnosisResult, DimensionScore, IssueOut
from app.services.parser import split_sections

logger = logging.getLogger(__name__)

DIMENSION_NAMES = ["项目深度", "技术广度", "表达结构", "成果量化", "岗位匹配"]
MAX_RESUME_CHARS = 12000

SYSTEM_PROMPT = """你是资深的技术面试官与简历顾问。请基于简历原文（可含目标 JD）给出诊断。

必须遵守：
1. 只依据简历中出现的文字，不得编造经历、公司或数字；
2. 每条 issue 的 quote 必须逐字摘自简历；找不到合适原文就留空字符串；
3. dimension_scores 固定包含且仅包含：项目深度、技术广度、表达结构、成果量化、岗位匹配；
4. 每项 0-100 整数；overall_score 为综合分；
5. issues 最多 6 条，按严重程度排序，severity 只能是 high / medium / low；
6. type 使用以下英文枚举之一：quantification, structure, relevance, depth, completeness, wording；
7. 只输出 JSON 对象，不要 markdown 代码块，不要额外解释。

JSON 结构：
{
  "overall_score": 0,
  "summary": "不超过 300 字的中文总评",
  "dimension_scores": [{"name": "项目深度", "score": 0}],
  "issues": [{
    "type": "quantification",
    "severity": "high",
    "dimension": "成果量化",
    "quote": "简历原文",
    "problem": "问题说明",
    "rewritten": "可直接替换的改写"
  }]
}"""


class DiagnosisError(Exception):
    """诊断失败；status_code 由路由层透传（503 配置缺失 / 502 上游异常）。"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _clamp(value: Any, low: int = 0, high: int = 100) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n……（内容过长已截断）"


def _build_messages(resume_text: str, jd_text: str | None) -> list[dict[str, str]]:
    jd_block = f"<jd>\n{_truncate(jd_text.strip(), 3000)}\n</jd>" if jd_text and jd_text.strip() else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "以下是简历原文与目标 JD。请按要求输出 JSON。\n\n"
                f"<resume>\n{_truncate(resume_text, MAX_RESUME_CHARS)}\n</resume>\n"
                f"{jd_block}"
            ),
        },
    ]


def _normalize_result(result: DiagnosisResult) -> DiagnosisResult:
    """补齐缺失维度、裁剪 issues，保证前端渲染契约稳定。"""
    raw_scores = {item.name.strip(): item.score for item in result.dimension_scores}
    matched_names = [
        name
        for name in DIMENSION_NAMES
        if name in raw_scores or any(name[:2] in key for key in raw_scores)
    ]
    if len(matched_names) < 3:
        raise ValueError("dimension_scores 缺少规定维度")

    dimension_scores: list[DimensionScore] = []
    for name in DIMENSION_NAMES:
        score = raw_scores.get(name)
        if score is None:
            # 容忍 “岗位匹配度” 这类近义写法
            matched = next((v for k, v in raw_scores.items() if name[:2] in k), None)
            score = matched if matched is not None else 60
        dimension_scores.append(DimensionScore(name=name, score=_clamp(score)))

    issues = []
    for issue in result.issues[:6]:
        issues.append(
            IssueOut(
                type=issue.type or "completeness",
                severity=issue.severity,
                dimension=issue.dimension or "",
                quote=(issue.quote or "")[:300],
                problem=issue.problem.strip(),
                rewritten=(issue.rewritten or "").strip(),
            )
        )

    summary = result.summary.strip() or "本次诊断未返回总评。"
    return DiagnosisResult(
        overall_score=_clamp(result.overall_score),
        summary=summary,
        dimension_scores=dimension_scores,
        issues=issues,
    )


def _extract_json_object(raw: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象：兼容 ```json 围栏与前后附带解释的情况。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("模型返回为空")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise TypeError("模型未返回 JSON 对象")
    return data


def _sanitize_quotes(result: DiagnosisResult, resume_text: str) -> DiagnosisResult:
    """任何不在原文中的 quote 都视为编造，直接清空，避免伪造引用。"""
    compact_resume = re.sub(r"\s+", "", resume_text or "")
    issues = []
    for issue in result.issues:
        quote = (issue.quote or "").strip()
        if quote and re.sub(r"\s+", "", quote) not in compact_resume:
            logger.info("discard quote not found in resume")
            quote = ""
        issues.append(issue.model_copy(update={"quote": quote[:300]}))
    return result.model_copy(update={"issues": issues})


def run_diagnosis(resume_text: str, jd_text: str | None = None) -> tuple[DiagnosisResult, str]:
    """返回 (结构化结果, 模型名)。

    - 仅在显式 LLM_MOCK=true 时返回启发式结果（单测/离线 UI）；
    - 未配置 key 直接抛 503，不生成“假报告”；
    - 输出格式错误最多重试一次，仍失败抛 502；
    - 鉴权/限流/超时/网络/截断分别给出可读错误。
    """
    if settings.LLM_MOCK:
        return _heuristic_diagnosis(resume_text, jd_text), "heuristic-v1"

    api_key = (settings.LLM_API_KEY or "").strip()
    if not api_key:
        raise DiagnosisError("未配置 LLM_API_KEY，无法调用诊断模型", status_code=503)

    messages = _build_messages(resume_text, jd_text)
    last_error: Exception | None = None

    for attempt in range(2):
        content = ""
        try:
            response = chat(messages, max_tokens=2000 if attempt == 0 else 3000)
            content = response.content
            if response.finish_reason == "length":
                raise ValueError("模型输出被截断（finish_reason=length）")

            data = _extract_json_object(content)
            result = DiagnosisResult.model_validate(data)
            result = _sanitize_quotes(result, resume_text)
            return _normalize_result(result), response.model

        except (ValueError, TypeError, ValidationError) as exc:
            last_error = exc
            logger.warning("diagnosis output invalid (attempt %s): %s", attempt + 1, exc)
            if "截断" in str(exc) and attempt == 1:
                raise DiagnosisError("模型输出被截断，简历可能过长，请精简后重试", 502) from exc
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": content[:4000] or "{}"},
                    {
                        "role": "user",
                        "content": (
                            f"上一次输出不符合要求：{str(exc)[:300]}。"
                            "请只返回符合 schema 的 JSON 对象。"
                        ),
                    },
                ]
                continue
            break

        except LLMError as exc:
            raise DiagnosisError(str(exc), status_code=exc.status_code) from exc
        except Exception as exc:
            logger.exception("LLM diagnosis request failed")
            raise DiagnosisError("诊断服务暂时不可用，请稍后重试", 502) from exc

    raise DiagnosisError("模型输出格式不符合要求，已重试仍失败，请稍后再试", 502) from last_error


def _heuristic_diagnosis(resume_text: str, jd_text: str | None) -> DiagnosisResult:
    """显式 LLM_MOCK=true 时的确定性结果，仅用于单测/离线 UI，不作为线上兜底。"""
    text = resume_text or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sections = split_sections(text)
    projects = "\n".join(sections.get("projects", []))
    skills = "\n".join(sections.get("skills", []))
    experience = "\n".join(sections.get("experience", []))

    metric_hits = re.findall(r"\d+(?:\.\d+)?\s*(?:%|ms|s|万|w|k|qps|人|单|倍)", text, re.IGNORECASE)
    tech_terms = set(
        re.findall(
            r"\b(?:Java|Python|Go|MySQL|Redis|Kafka|Docker|Kubernetes|K8s|Spring|React|Vue|"
            r"Linux|TCP|HTTP|JVM|C\+\+|TypeScript)\b",
            text,
            re.IGNORECASE,
        )
    )
    skill_items = [item for item in re.split(r"[、,，/|]", skills) if item.strip()]

    scores = {
        "项目深度": _clamp(
            62
            + (10 if len(projects) > 120 else 0)
            + (6 if metric_hits else 0)
            + (4 if len(sections.get("projects", [])) >= 3 else 0)
        ),
        "技术广度": _clamp(58 + min(24, len(tech_terms) * 3)),
        "表达结构": _clamp(64 + (10 if len(lines) >= 12 else 0) + (4 if sections.get("education") else 0)),
        "成果量化": _clamp(46 + (24 if metric_hits else 0) + (6 if "%" in text else 0)),
        "岗位匹配": _clamp(60 + (14 if jd_text and jd_text.strip() else 0) + (6 if experience else 0)),
    }
    weights = {"项目深度": 0.25, "技术广度": 0.2, "表达结构": 0.15, "成果量化": 0.25, "岗位匹配": 0.15}
    overall = _clamp(sum(scores[name] * weight for name, weight in weights.items()))

    issues: list[IssueOut] = []

    def first_line_with(*keywords: str) -> str:
        matches = [line for line in lines if any(keyword in line for keyword in keywords)]
        # 取最长匹配：标题行往往也含“开发/项目”等词，直接取第一条会引用错
        return (max(matches, key=len) if matches else (lines[0] if lines else ""))[:200]

    if scores["成果量化"] < 72:
        quote = first_line_with("负责", "参与", "优化", "开发", "搭建")
        issues.append(
            IssueOut(
                type="quantification",
                severity="high",
                dimension="成果量化",
                quote=quote,
                problem="描述以职责为主，缺少可验证的结果指标（延迟、吞吐、规模、收益）。",
                rewritten=(
                    "把结果补成「动作 + 指标 + 影响范围」：例如将接口 P99 从 X ms 降至 Y ms，"
                    "支撑日均 N 单/峰值 QPS M。"
                ),
            )
        )

    if len(projects) < 100:
        quote = first_line_with("项目", "系统", "平台")
        issues.append(
            IssueOut(
                type="depth",
                severity="high" if len(projects) < 50 else "medium",
                dimension="项目深度",
                quote=quote,
                problem="项目描述偏薄，缺少技术选型理由、难点与取舍，面试官难以判断你的实际贡献。",
                rewritten="补充「背景 → 难点 → 方案取舍 → 结果」四段，至少写出一个你独立负责的技术决策。",
            )
        )

    if len(skill_items) >= 10 or len(skills) > 120:
        issues.append(
            IssueOut(
                type="structure",
                severity="medium",
                dimension="表达结构",
                quote=skills[:200],
                problem="技能平铺罗列、没有熟练度分层，招聘方无法快速定位你的强项。",
                rewritten="按「主力 / 熟悉 / 了解」分层，每层只保留 3-5 个与目标岗位相关的技术。",
            )
        )

    if len(lines) < 10:
        issues.append(
            IssueOut(
                type="completeness",
                severity="low",
                dimension="信息完整",
                quote=(lines[0] if lines else "")[:200],
                problem="简历信息量偏少，缺少项目规模、角色与技术难点的最小信息集。",
                rewritten="至少补齐教育、项目、技能三段，并标注时间、角色与项目规模。",
            )
        )

    if not issues:
        issues.append(
            IssueOut(
                type="wording",
                severity="low",
                dimension="表达结构",
                quote=(lines[0] if lines else "")[:200],
                problem="整体结构完整，可进一步把动词换成更有结果感的表达，并保持每条经历一个重点。",
                rewritten="将「负责/参与」替换为「主导/设计/落地」，每条经历只保留一个最亮的结果。",
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda item: order[item.severity])

    weak_dimensions = [name for name, score in scores.items() if score < 70]
    summary = (
        f"整体得分 {overall}，"
        + (f"相对薄弱的是{'、'.join(weak_dimensions)}。" if weak_dimensions else "各维度较均衡。")
        + ("已给出针对性的改写建议。" if issues else "")
        + "（启发式调试模式，仅用于本地测试。）"
    )

    return DiagnosisResult(
        overall_score=overall,
        summary=summary[:500],
        dimension_scores=[DimensionScore(name=name, score=score) for name, score in scores.items()],
        issues=issues,
    )
