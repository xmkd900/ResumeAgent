from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import DiagnosisReport, Resume, ResumeClaim, User
from app.schemas.interview import ResumeClaimOut
from app.schemas.resume import (
    DiagnoseRequest,
    DimensionScore,
    IssueOut,
    ReportListOut,
    ReportOut,
    ReportSummaryOut,
    ResumeListOut,
    ResumeOut,
)
from app.services.claim_extraction import ClaimExtractionError, extract_claims, sync_claims
from app.services.diagnosis import DiagnosisError, run_diagnosis
from app.services.parser import parse_resume_task
from app.services.storage import save_upload

router = APIRouter(prefix="/resumes", tags=["resumes"])


def get_owned_resume(db: Session, resume_id: int, user_id: int) -> Resume:
    """所有按 id 的访问都必须带 user_id；不区分“不存在”和“不是你的”。"""
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    return resume


def to_resume_out(resume: Resume) -> ResumeOut:
    latest = resume.latest_report
    return ResumeOut(
        id=resume.id,
        filename=resume.filename,
        parse_status=resume.parse_status,
        parse_error=resume.parse_error,
        file_size=resume.file_size,
        created_at=resume.created_at,
        latest_report=ReportSummaryOut.model_validate(latest) if latest else None,
    )


def to_report_out(report: DiagnosisReport) -> ReportOut:
    return ReportOut(
        id=report.id,
        resume_id=report.resume_id,
        jd_id=report.jd_id,
        has_jd=report.has_jd,
        overall_score=report.overall_score,
        summary=report.summary,
        dimension_scores=[DimensionScore(**item) for item in report.dimension_scores],
        issues=[IssueOut(**item) for item in report.issues],
        created_at=report.created_at,
    )


@router.post("/upload", response_model=ResumeOut, status_code=201)
async def upload_resume(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = await save_upload(file, user.id)
    resume = Resume(
        user_id=user.id,
        filename=saved.filename,
        file_path=str(saved.path),
        file_size=saved.size,
        parse_status="pending",
    )
    try:
        db.add(resume)
        db.commit()
        db.refresh(resume)
    except Exception:
        db.rollback()
        saved.path.unlink(missing_ok=True)
        raise

    background.add_task(parse_resume_task, resume.id)
    return to_resume_out(resume)


@router.get("", response_model=ResumeListOut)
def list_resumes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    where = Resume.user_id == user.id
    total = db.scalar(select(func.count(Resume.id)).where(where)) or 0
    resumes = db.scalars(
        select(Resume)
        .where(where)
        .options(selectinload(Resume.reports))
        .order_by(Resume.created_at.desc(), Resume.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ResumeListOut(items=[to_resume_out(item) for item in resumes], total=total)


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return to_resume_out(get_owned_resume(db, resume_id, user.id))


@router.get("/{resume_id}/claims", response_model=list[ResumeClaimOut])
def list_resume_claims(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = get_owned_resume(db, resume_id, user.id)
    rows = db.scalars(
        select(ResumeClaim)
        .where(ResumeClaim.resume_id == resume.id)
        .order_by(ResumeClaim.id)
    ).all()
    return [ResumeClaimOut.model_validate(row) for row in rows]


@router.post("/{resume_id}/claims/extract", response_model=list[ResumeClaimOut])
def extract_resume_claims(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从已解析简历抽取可追问事实；没有证据的 claim 会被丢弃。"""
    resume = get_owned_resume(db, resume_id, user.id)
    if resume.parse_status != "done" or not resume.raw_text:
        raise HTTPException(status_code=409, detail="简历尚未解析完成")

    try:
        claims = extract_claims(resume.raw_text)
    except ClaimExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    rows = sync_claims(db, resume.id, claims)
    return [ResumeClaimOut.model_validate(row) for row in rows]


@router.post("/{resume_id}/reparse", response_model=ResumeOut)
def reparse_resume(
    resume_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解析失败或任务中断后，用已上传的原文件重试，避免用户重复上传。"""
    resume = get_owned_resume(db, resume_id, user.id)
    if resume.parse_status == "pending":
        # 任务仍在跑时拒绝重复触发；超过 2 分钟视为疑似卡死，允许重试
        age = (datetime.now() - resume.created_at).total_seconds()
        if age < 120:
            raise HTTPException(status_code=409, detail="简历正在解析中，请稍后再试")
    if not Path(resume.file_path).exists():
        raise HTTPException(status_code=410, detail="原始文件已丢失，请重新上传")

    resume.parse_status = "pending"
    resume.parse_error = None
    db.commit()
    db.refresh(resume)
    background.add_task(parse_resume_task, resume.id)
    return to_resume_out(resume)


@router.post("/{resume_id}/diagnose", response_model=ReportOut)
def diagnose_resume(
    resume_id: int,
    body: DiagnoseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = get_owned_resume(db, resume_id, user.id)
    if resume.parse_status != "done" or not resume.raw_text:
        raise HTTPException(status_code=409, detail="简历尚未解析完成")

    try:
        result, model_name = run_diagnosis(resume.raw_text, body.jd_text)
    except DiagnosisError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    report = DiagnosisReport(
        resume_id=resume.id,
        has_jd=bool(body.jd_text and body.jd_text.strip()),
        overall_score=result.overall_score,
        dimension_scores=[item.model_dump() for item in result.dimension_scores],
        issues=[item.model_dump() for item in result.issues],
        summary=result.summary,
        model=model_name,
        prompt_version=settings.DIAGNOSIS_PROMPT_VERSION,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return to_report_out(report)


@router.get("/{resume_id}/reports", response_model=ReportListOut)
def list_reports(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = get_owned_resume(db, resume_id, user.id)
    reports = db.scalars(
        select(DiagnosisReport)
        .where(DiagnosisReport.resume_id == resume.id)
        .order_by(DiagnosisReport.created_at.desc(), DiagnosisReport.id.desc())
    ).all()
    return ReportListOut(items=[to_report_out(item) for item in reports], total=len(reports))
