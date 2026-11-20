from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.growth import (
    FixRequest,
    FixResultOut,
    GapCardOut,
    PracticeRequest,
    PracticeResultOut,
    ReviewRequest,
    ReviewResultOut,
    WeakPointExercisesOut,
    WeakPointListOut,
    WeakPointOut,
    WeakPointQueueOut,
)
from app.services import growth
from app.services.growth import GrowthError

router = APIRouter(prefix="/weak-points", tags=["growth"])


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=getattr(exc, "status_code", 409), detail=str(exc)
    )


@router.get("", response_model=WeakPointListOut)
def list_points(
    include_resolved: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """薄弱点列表：按"未解决 → 严重度 → 复发次数"排序，附概览统计。"""
    items = growth.list_weak_points(
        db, user_id=user.id, include_resolved=include_resolved
    )
    return WeakPointListOut(
        items=[growth.to_out(item) for item in items],
        stats=growth.build_stats(db, user_id=user.id, items=items),
        total=len(items),
    )


@router.get("/queue", response_model=WeakPointQueueOut)
def queue(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """今日队列：待修复的缺口 + 今天到期复查的项。"""
    return growth.build_queue(db, user_id=user.id)


@router.get("/{weak_point_id}/gap", response_model=GapCardOut)
def gap_card(
    weak_point_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """缺口卡：原题、原话、缺的那一条、建议补法与复查题预览。"""
    try:
        return growth.build_gap_card(
            db, user_id=user.id, weak_point_id=weak_point_id
        )
    except GrowthError as exc:
        raise _http_error(exc) from exc


@router.post("/{weak_point_id}/fix", response_model=FixResultOut)
def fix(
    weak_point_id: int,
    payload: FixRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """只补缺口（1-3 句），通过后进入 1 天后的复查。"""
    try:
        return growth.submit_fix(
            db,
            user_id=user.id,
            weak_point_id=weak_point_id,
            answer=payload.answer,
        )
    except GrowthError as exc:
        raise _http_error(exc) from exc


@router.post("/{weak_point_id}/review", response_model=ReviewResultOut)
def review(
    weak_point_id: int,
    payload: ReviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """变体题复查：看这条缺口是否真的记住了。"""
    try:
        return growth.submit_review(
            db,
            user_id=user.id,
            weak_point_id=weak_point_id,
            answer=payload.answer,
            question_id=payload.question_id,
        )
    except GrowthError as exc:
        raise _http_error(exc) from exc


@router.get("/{weak_point_id}/exercises", response_model=WeakPointExercisesOut)
def exercises(
    weak_point_id: int,
    with_content: bool = Query(
        default=True, description="false 时不调模型，只返回题库推荐的降级讲解（列表预取用）"
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """练习视图：讲解（带来源）+ 推荐练习（按掌握度选难度）。"""
    try:
        return growth.build_exercises(
            db,
            user_id=user.id,
            weak_point_id=weak_point_id,
            with_content=with_content,
        )
    except GrowthError as exc:
        raise _http_error(exc) from exc


@router.post("/{weak_point_id}/practice", response_model=PracticeResultOut)
def practice(
    weak_point_id: int,
    payload: PracticeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交复述：判卷后只更新掌握度，不新增薄弱点。"""
    try:
        return growth.submit_practice(
            db,
            user_id=user.id,
            weak_point_id=weak_point_id,
            answer=payload.answer,
            question_id=payload.question_id,
        )
    except GrowthError as exc:
        raise _http_error(exc) from exc


@router.post("/{weak_point_id}/resolve", response_model=WeakPointOut)
def resolve(
    weak_point_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标记已掌握：掌握度置 100、移出待攻克列表；复发会重新打开。"""
    try:
        return growth.resolve_weak_point(
            db, user_id=user.id, weak_point_id=weak_point_id
        )
    except GrowthError as exc:
        raise _http_error(exc) from exc
