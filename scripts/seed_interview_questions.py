"""导入面试题库种子。

用法：
    uv run python scripts/seed_interview_questions.py --dry-run
    uv run python scripts/seed_interview_questions.py
    uv run python scripts/seed_interview_questions.py --file src/app/seed/backend.jsonl
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from app.db.session import SessionLocal
from app.services.question_seed import (
    DEFAULT_SEED_DIR,
    SeedError,
    load_seed_dir,
    load_seed_file,
    upsert_questions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入面试题库 JSONL 种子")
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="只导入单个 JSONL 文件；不传则导入 seed 目录下全部文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只校验并统计，不写数据库",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        seeds = load_seed_file(args.file) if args.file else load_seed_dir(DEFAULT_SEED_DIR)
    except SeedError as exc:
        print(f"[seed] 校验失败：{exc}", file=sys.stderr)
        return 2

    print(f"[seed] 校验通过：{len(seeds)} 道题")
    print(f"[seed] 领域分布：{dict(Counter(seed.domain for seed in seeds))}")
    print(f"[seed] 难度分布：{dict(Counter(seed.difficulty for seed in seeds))}")

    if args.dry_run:
        print("[seed] dry-run，不写数据库")
        return 0

    db = SessionLocal()
    try:
        result = upsert_questions(db, seeds)
    except Exception as exc:  # noqa: BLE001  CLI 需要把数据库错误完整抛给调用者
        db.rollback()
        print(f"[seed] 写入失败：{exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"[seed] 完成：{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
