"""题库种子导入：JSONL → Pydantic 校验 → MySQL 幂等 upsert。

题库是主数据，Qdrant 只是索引；这个模块不碰向量库。
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InterviewQuestion
from app.schemas.interview import QuestionSeed

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
DEFAULT_SEED_DIR = SEED_DIR


class SeedError(Exception):
    """种子文件格式或内容不合法。"""


@dataclass
class SeedResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0

    def __str__(self) -> str:
        return (
            f"created={self.created} updated={self.updated} "
            f"unchanged={self.unchanged} skipped={self.skipped}"
        )


def load_seed_file(path: Path) -> list[QuestionSeed]:
    seeds: list[QuestionSeed] = []
    seen: set[tuple[str, str]] = set()

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
            seed = QuestionSeed.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SeedError(f"{path.name}:{line_no}: {exc}") from exc

        if not seed.rubric.get("must"):
            raise SeedError(f"{path.name}:{line_no}: rubric.must 不能为空")

        key = (seed.domain, seed.content)
        if key in seen:
            raise SeedError(f"{path.name}:{line_no}: 重复题目 {seed.domain} / {seed.content[:30]}")
        seen.add(key)
        seeds.append(seed)

    return seeds


def load_seed_dir(directory: Path = DEFAULT_SEED_DIR) -> list[QuestionSeed]:
    if not directory.exists():
        raise SeedError(f"种子目录不存在：{directory}")
    seeds: list[QuestionSeed] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(directory.glob("*.jsonl")):
        for seed in load_seed_file(path):
            key = (seed.domain, seed.content)
            if key in seen:
                raise SeedError(f"跨文件重复题目：{seed.domain} / {seed.content[:30]}")
            seen.add(key)
            seeds.append(seed)
    if not seeds:
        raise SeedError(f"种子目录没有 .jsonl 文件：{directory}")
    return seeds


def upsert_question(db: Session, seed: QuestionSeed) -> str:
    """按 (domain, content) 幂等写入；返回 created/updated/unchanged/skipped。"""
    existing = db.scalar(
        select(InterviewQuestion).where(
            InterviewQuestion.domain == seed.domain,
            InterviewQuestion.content == seed.content,
        )
    )
    payload = seed.model_dump()

    if existing is None:
        db.add(
            InterviewQuestion(
                **payload,
                source="manual",
                status="published",
                version=1,
            )
        )
        return "created"

    if existing.status == "retired":
        return "skipped"

    changed = any(getattr(existing, key) != value for key, value in payload.items())
    if not changed:
        return "unchanged"

    for key, value in payload.items():
        setattr(existing, key, value)
    existing.version += 1
    return "updated"


def upsert_questions(db: Session, seeds: list[QuestionSeed]) -> SeedResult:
    result = SeedResult()
    for seed in seeds:
        outcome = upsert_question(db, seed)
        setattr(result, outcome, getattr(result, outcome) + 1)
    db.commit()
    return result
