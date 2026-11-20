"""回放历史回答，用当前判卷口径重新打分（调 prompt / 校准用）。

用途：
    uv run python scripts/replay_judge.py --session 21 --session 10

输出每轮「旧分 → 新分」对照，用来验证"水答案不再拿高分"，
同时避免改 prompt 时把扎实的回答一起压下去。
"""

import argparse
import re

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import InterviewSession, InterviewTurn
from app.services.interview_judge import judge_answer


def _one_line(text: str, limit: int = 46) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="回放历史面试回答并重新判卷")
    parser.add_argument("--session", type=int, action="append", required=True)
    parser.add_argument("--limit", type=int, default=0, help="最多回放多少轮（0 = 全部）")
    args = parser.parse_args()

    db = SessionLocal()
    rows = 0
    deltas: list[tuple[int, int]] = []
    try:
        print(
            "session\tturn\tdepth\tcompetency\told\tnew\tverdict\t"
            "cov-spec-reas-auth-clar\tcapped_by\tanswer"
        )
        for session_id in args.session:
            session = db.get(InterviewSession, session_id)
            if session is None:
                print(f"# session {session_id} 不存在", flush=True)
                continue
            turns = list(
                db.scalars(
                    select(InterviewTurn)
                    .where(
                        InterviewTurn.session_id == session_id,
                        InterviewTurn.answer.is_not(None),
                    )
                    .order_by(InterviewTurn.turn_index)
                ).all()
            )
            for turn in turns:
                if args.limit and rows >= args.limit:
                    break
                result = judge_answer(
                    question=turn.question,
                    expected_points=list(turn.expected_points or []),
                    rubric=dict(turn.rubric or {}),
                    answer=turn.answer or "",
                    position=session.position,
                    depth=turn.depth,
                )
                old = turn.score if turn.score is not None else 0
                deltas.append((old, result.score))
                rows += 1
                dims = result.dimensions
                dim_text = "-".join(str(dims.get(key, 0)) for key in (
                    "coverage", "specificity", "reasoning", "authenticity", "clarity"
                ))
                print(
                    f"{session_id}\t{turn.turn_index}\t{turn.depth}\t{turn.competency}\t"
                    f"{old}\t{result.score}\t{result.verdict}\t{dim_text}\t"
                    f"{result.capped_by or '-'}\t{_one_line(turn.answer or '')}",
                    flush=True,
                )
    finally:
        db.close()

    if deltas:
        old_avg = sum(old for old, _ in deltas) / len(deltas)
        new_avg = sum(new for _, new in deltas) / len(deltas)
        print(f"\n# 轮次 {len(deltas)}  旧均分 {old_avg:.1f}  新均分 {new_avg:.1f}")


if __name__ == "__main__":
    main()
