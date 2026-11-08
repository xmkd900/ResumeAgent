"""单轮判卷：只做文本判断，不碰数据库、不决定下一题。"""

import logging

from pydantic import ValidationError

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.llm.json import extract_json_object
from app.schemas.interview import JudgementOut

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """你是技术面试的判卷器。只根据题目、评分要点和候选人回答给结论。

评分口径（score，0-100）：
- 85-100：覆盖大部分要点，有因果/取舍/验证，能支撑"做过"；
- 60-84：方向正确，但缺关键细节或只给结论；
- 30-59：只答对零散概念，或答非所问；
- 0-29：空白、跑题、明显错误。

规则：
1. 只依据候选人实际说出的内容，不脑补，不因表达风格扣分；
2. hit_points 必须能在回答中找到依据；
3. missing_points 只能从 expected_points 中选，不要新增；
4. verdict 与 score 必须一致：good≥85，partial 60-84，bad<60；
5. followup_hint 写"还值得追问的那一个点"，一句话，没有就留空；
6. feedback 不超过 100 字，指出最关键的优点或缺口；
7. 只输出 JSON，不要 markdown，不要解释。

JSON 结构：
{
  "verdict": "good | partial | bad",
  "score": 0,
  "hit_points": ["..."],
  "missing_points": ["..."],
  "followup_hint": "...",
  "feedback": "..."
}"""


class JudgeError(Exception):
    """判卷服务异常。
    
    Attributes:
        status_code: HTTP状态码，默认502
    """
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def judge_answer(
    *,
    question: str,
    expected_points: list[str] | None,
    rubric: dict | None,
    answer: str,
) -> JudgementOut:
    """对一轮回答判卷；格式错误重试一次，失败抛 JudgeError。
    
    Args:
        question: 问题文本
        expected_points: 期望得分点列表
        rubric: 评分标准字典
        answer: 候选人回答文本
    
    Returns:
        JudgementOut对象，包含：
        - verdict: 评价等级（good/partial/bad）
        - score: 分数（0-100）
        - hit_points: 命中的要点
        - missing_points: 缺失的要点
        - followup_hint: 追问提示
        - feedback: 反馈意见
    
    Raises:
        JudgeError: 判卷失败或格式错误
    """
    if not (settings.LLM_API_KEY or "").strip():
        raise JudgeError("未配置 LLM_API_KEY，无法调用判卷模型", status_code=503)

    points = [str(item).strip() for item in (expected_points or []) if str(item).strip()]
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"<question>\n{question}\n</question>\n"
                f"<expected_points>\n{points}\n</expected_points>\n"
                f"<rubric>\n{rubric or {}}\n</rubric>\n"
                f"<answer>\n{answer[:4000]}\n</answer>"
            ),
        },
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        content = ""
        try:
            response = chat(messages, max_tokens=900, temperature=0.1)
            content = response.content
            judgement = JudgementOut.model_validate(extract_json_object(content))
            return _sanitize(judgement, points)
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
                            "请只返回 verdict/score/hit_points/missing_points/"
                            "followup_hint/feedback 的 JSON。"
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


def _sanitize(judgement: JudgementOut, allowed_points: list[str]) -> JudgementOut:
    """清洗判卷结果：去重、限制条数，并保证 verdict 与 score 自洽。
    
    Args:
        judgement: LLM返回的原始判卷结果
        allowed_points: 允许的得分点列表（用于过滤缺失点）
    
    Returns:
        清洗后的 JudgementOut 对象
    """
    allowed = set(allowed_points)

    hits: list[str] = []
    for item in judgement.hit_points:
        text = str(item).strip()
        if text and text not in hits:
            hits.append(text)

    missing: list[str] = []
    for item in judgement.missing_points:
        text = str(item).strip()
        if not text or text in missing:
            continue
        # 允许模型用原文表述，也允许略作改写；只要与某个要点有交集就保留
        if not allowed or text in allowed or any(text in point or point in text for point in allowed):
            missing.append(text)

    score = max(0, min(100, int(judgement.score or 0)))
    if score == 0 and judgement.verdict:
        # 模型只给档位没给分时，用档位中位数兜底，避免全 0 让总分成噪声
        score = {"good": 88, "partial": 72, "bad": 45}.get(judgement.verdict, 50)

    verdict = judgement.verdict
    if verdict == "good" and score < 85:
        verdict = "partial"
    elif verdict == "partial" and (score >= 85 or score < 60):
        verdict = "good" if score >= 85 else "bad"
    elif verdict == "bad" and score >= 60:
        verdict = "partial"

    return judgement.model_copy(
        update={
            "verdict": verdict,
            "score": score,
            "hit_points": hits[:6],
            "missing_points": missing[:6],
            "followup_hint": (judgement.followup_hint or "").strip()[:160],
            "feedback": (judgement.feedback or "").strip()[:200],
        }
    )
