from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.interview import (
    AnswerRequest,
    AnswerResponse,
    InterviewCreateRequest,
    InterviewListOut,
    InterviewSessionDetailOut,
    InterviewSessionOut,
)
from app.services.interview import (
    InterviewError,
    abort_interview,
    create_interview,
    finish_interview,
    get_interview_detail,
    list_interviews,
    pause_interview,
    resume_interview,
    submit_answer,
)
from app.services.interview_director import DirectorError
from app.services.interview_judge import JudgeError

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _http_error(exc: Exception) -> HTTPException:
    status = getattr(exc, "status_code", 409)
    return HTTPException(status_code=status, detail=str(exc))


@router.post("", response_model=InterviewSessionDetailOut, status_code=201)
def create(
    payload: InterviewCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return create_interview(
            db,
            user_id=user.id,
            position=payload.position,
            resume_id=payload.resume_id,
            jd_text=payload.jd_text,
            max_questions=payload.max_questions,
        )
    except (InterviewError, DirectorError) as exc:
        raise _http_error(exc) from exc


@router.get("", response_model=InterviewListOut)
def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = list_interviews(db, user_id=user.id, page=page, page_size=page_size)
    return InterviewListOut(
        items=[InterviewSessionOut.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/{session_id}", response_model=InterviewSessionDetailOut)
def detail(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return get_interview_detail(db, user_id=user.id, session_id=session_id)
    except InterviewError as exc:
        raise _http_error(exc) from exc


@router.post("/{session_id}/answer", response_model=AnswerResponse)
def answer(
    session_id: int,
    payload: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return submit_answer(
            db,
            user_id=user.id,
            session_id=session_id,
            answer=payload.answer,
        )
    except (InterviewError, JudgeError, DirectorError) as exc:
        raise _http_error(exc) from exc


@router.post("/{session_id}/pause", response_model=InterviewSessionDetailOut)
def pause(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return pause_interview(db, user_id=user.id, session_id=session_id)
    except InterviewError as exc:
        raise _http_error(exc) from exc


@router.post("/{session_id}/resume", response_model=InterviewSessionDetailOut)
def resume(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return resume_interview(db, user_id=user.id, session_id=session_id)
    except InterviewError as exc:
        raise _http_error(exc) from exc


@router.post("/{session_id}/finish", response_model=InterviewSessionDetailOut)
def finish(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return finish_interview(db, user_id=user.id, session_id=session_id)
    except (InterviewError, JudgeError, DirectorError) as exc:
        raise _http_error(exc) from exc


@router.post("/{session_id}/abort", response_model=InterviewSessionDetailOut)
def abort(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return abort_interview(db, user_id=user.id, session_id=session_id)
    except InterviewError as exc:
        raise _http_error(exc) from exc
