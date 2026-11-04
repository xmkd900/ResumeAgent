from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DimensionScore(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)

class IssueOut(BaseModel):
    type: str
    severity: Literal["high", "medium", "low"]
    dimension: str = ""
    quote: str = ""
    problem: str
    rewritten: str = ""

class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    overall_score: int
    created_at: datetime

class ResumeOut(BaseModel):
    id: int
    filename: str
    parse_status: Literal["pending", "done", "failed"]
    parse_error: str | None = None
    file_size: int
    created_at: datetime
    latest_report: ReportSummaryOut | None = None

class ReportOut(BaseModel):
    id: int
    resume_id: int
    jd_id: int | None = None
    has_jd: bool = False
    overall_score: int
    summary: str
    dimension_scores: list[DimensionScore]
    issues: list[IssueOut]
    created_at: datetime

class ResumeListOut(BaseModel):
    items: list[ResumeOut]
    total: int

class ReportListOut(BaseModel):
    items: list[ReportOut]
    total: int

class DiagnoseRequest(BaseModel):
    jd_text: str | None = Field(default=None, max_length=4000)

class DiagnosisResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=5, max_length=500)
    dimension_scores: list[DimensionScore] = Field(min_length=3, max_length=8)
    issues: list[IssueOut] = Field(min_length=0, max_length=8)