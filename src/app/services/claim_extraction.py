"""从简历原文抽取可追问事实（resume_claim）。

硬约束：
- 每条 claim 必须绑定能在原文中匹配的 evidence_quote；
- 技术标签必须出现在引文中；
- 不做“没证据也硬抽”的兜底，抽不到就明确报错。
"""

import logging
import re

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.llm.json import extract_json_object
from app.models import ResumeClaim
from app.schemas.interview import ClaimDraft, ClaimExtraction

logger = logging.getLogger(__name__)

MAX_RESUME_CHARS = 12000
MAX_CLAIMS = 12

SYSTEM_PROMPT = """你是简历事实抽取器。请从简历原文中抽取可用于面试追问的事实。

规则：
1. 只能抽取简历中明确出现的内容，不能推断或编造公司、项目、指标、技术；
2. evidence_quote 必须逐字摘自简历，不能改写、拼接或补全；
3. claim_type 只能是 project / experience / skill / metric；
4. tech_tags 只能填写 evidence_quote 中出现的词；
5. metrics 只填写引文中明确出现的数字及其含义；
6. 抽取 6-12 条，优先项目、关键技术、可量化结果；
7. 只输出 JSON 对象，不要 markdown 代码块，不要解释。

JSON 结构：
{
  "claims": [
    {
      "claim_type": "project",
      "title": "订单系统",
      "evidence_quote": "负责订单与支付对账模块",
      "tech_tags": ["MySQL", "Redis"],
      "metrics": {"orders_per_day": 800},
      "role": "后端开发",
      "confidence": 0.9
    }
  ]
}"""


class ClaimExtractionError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _validate_claims(claims: list[ClaimDraft], resume_text: str) -> list[ClaimDraft]:
    compact_resume = _compact(resume_text)
    result: list[ClaimDraft] = []
    seen: set[tuple[str, str]] = set()

    for claim in claims:
        quote = claim.evidence_quote.strip()
        title = claim.title.strip()
        if not title or len(quote) < 6 or _compact(quote) not in compact_resume:
            logger.info("discard claim without verifiable evidence: %s", title or "<empty>")
            continue

        key = (claim.claim_type, title.casefold())
        if key in seen:
            continue
        seen.add(key)

        # 只保留确实出现在引文里的技术词，防止模型补充简历没有的技术
        tags = [
            tag.strip()
            for tag in claim.tech_tags
            if tag.strip() and tag.strip().casefold() in quote.casefold()
        ]
        result.append(
            claim.model_copy(
                update={
                    "title": title,
                    "evidence_quote": quote,
                    "tech_tags": tags,
                }
            )
        )
        if len(result) >= MAX_CLAIMS:
            break

    return result


def extract_claims(resume_text: str) -> list[ClaimDraft]:
    """调用模型抽取 claims；格式错误重试一次，仍失败明确报错。"""
    if not (settings.LLM_API_KEY or "").strip():
        raise ClaimExtractionError("未配置 LLM_API_KEY，无法抽取简历事实", status_code=503)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "以下是简历原文。请抽取可验证的事实，只返回 JSON。\n\n"
                f"<resume>\n{resume_text[:MAX_RESUME_CHARS]}\n</resume>"
            ),
        },
    ]
    last_error: Exception | None = None

    for attempt in range(2):
        content = ""
        try:
            response = chat(messages, max_tokens=1800 if attempt == 0 else 2500)
            content = response.content
            if response.finish_reason == "length":
                raise ValueError("模型输出被截断")

            data = extract_json_object(content)
            parsed = ClaimExtraction.model_validate(data)
            claims = _validate_claims(parsed.claims, resume_text)
            if not claims:
                raise ValueError("模型没有返回可验证的简历事实")
            return claims

        except (ValueError, TypeError, ValidationError) as exc:
            last_error = exc
            logger.warning("claim extraction invalid (attempt %s): %s", attempt + 1, exc)
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": content[:4000] or "{}"},
                    {
                        "role": "user",
                        "content": (
                            f"上一次输出不符合要求：{str(exc)[:300]}。"
                            "请只返回符合 schema、且 evidence_quote 能在简历中逐字找到的 JSON。"
                        ),
                    },
                ]
                continue
        except LLMError as exc:
            raise ClaimExtractionError(str(exc), status_code=exc.status_code) from exc
        except Exception as exc:
            logger.exception("claim extraction failed")
            raise ClaimExtractionError("简历事实抽取失败，请稍后重试", status_code=502) from exc

    raise ClaimExtractionError(
        "模型返回的简历事实不符合要求，已重试仍失败", status_code=502
    ) from last_error


def sync_claims(db: Session, resume_id: int, claims: list[ClaimDraft]) -> list[ResumeClaim]:
    """按 (claim_type, title) 同步：保留稳定 ID，删除本次未出现的旧 claim。"""
    existing = db.scalars(
        select(ResumeClaim).where(ResumeClaim.resume_id == resume_id)
    ).all()
    by_key = {(row.claim_type, row.title.casefold()): row for row in existing}
    seen: set[tuple[str, str]] = set()

    for claim in claims:
        key = (claim.claim_type, claim.title.casefold())
        row = by_key.get(key)
        if row is None:
            row = ResumeClaim(resume_id=resume_id, claim_type=claim.claim_type, title=claim.title)
            db.add(row)
        row.title = claim.title
        row.evidence_quote = claim.evidence_quote
        row.tech_tags = claim.tech_tags
        row.metrics = claim.metrics
        row.role = claim.role
        row.confidence = claim.confidence
        seen.add(key)

    for key, row in by_key.items():
        if key not in seen:
            db.delete(row)

    db.commit()
    return list(
        db.scalars(
            select(ResumeClaim)
            .where(ResumeClaim.resume_id == resume_id)
            .order_by(ResumeClaim.id)
        ).all()
    )
