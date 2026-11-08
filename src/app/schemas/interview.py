from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimType = Literal["project", "experience", "skill", "metric"]
QuestionSource = Literal["resume", "bank", "jd", "generated"]
QuestionType = Literal["concept", "scenario", "project", "behavioral"]
Difficulty = Literal["junior", "mid", "senior"]
SessionStatus = Literal["ongoing", "paused", "finished", "aborted"]
TurnAction = Literal["open", "ask", "followup", "legacy"]
Verdict = Literal["good", "partial", "bad"]


class ResumeClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_type: ClaimType
    title: str
    evidence_quote: str
    tech_tags: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    role: str | None = None
    confidence: float = 0.0

    @field_validator("tech_tags", mode="before")
    @classmethod
    def _none_tags_to_list(cls, value):
        return value or []

    @field_validator("metrics", mode="before")
    @classmethod
    def _none_metrics_to_dict(cls, value):
        return value or {}


class ClaimDraft(BaseModel):
    """LLM 抽取的单条简历事实；evidence_quote 必须能在简历原文中找到。"""

    claim_type: ClaimType
    title: str = Field(min_length=1, max_length=255)
    evidence_quote: str = Field(min_length=6)
    tech_tags: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    role: str | None = Field(default=None, max_length=128)
    confidence: float = Field(default=0.6, ge=0, le=1)


class ClaimExtraction(BaseModel):
    claims: list[ClaimDraft] = Field(min_length=1, max_length=20)


class QuestionSeed(BaseModel):
    """题库种子文件的单条记录；导入脚本负责校验后写 MySQL。"""

    domain: Literal["backend", "frontend", "agent", "common"]
    position: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=64)
    competency: str = Field(min_length=1, max_length=64)
    question_type: QuestionType
    difficulty: Difficulty
    content: str = Field(min_length=8)
    expected_points: list[str] = Field(min_length=1)
    rubric: dict = Field(default_factory=dict)
    followup_chain: list[str] = Field(default_factory=list)
    probe_dimensions: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=0, le=5)
    tags: list[str] = Field(default_factory=list)


class InterviewCreateRequest(BaseModel):
    position: str = Field(min_length=1, max_length=64)
    resume_id: int | None = None
    jd_id: int | None = None
    jd_text: str | None = Field(default=None, max_length=4000)
    # 允许调用方收紧/放宽预算；实际题数仍由面试官按对话决定
    max_questions: int | None = Field(default=None, ge=4, le=20)


class JudgementOut(BaseModel):
    verdict: Verdict
    score: int = Field(default=0, ge=0, le=100)
    hit_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    followup_hint: str = ""
    feedback: str = ""


class CurrentQuestionOut(BaseModel):
    turn_id: int
    turn_index: int
    depth: int
    content: str
    competency: str
    source: QuestionSource
    action: Literal["open", "ask", "followup", "legacy"] = "ask"


class InterviewTurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    turn_index: int
    action: TurnAction
    source: QuestionSource
    depth: int
    competency: str
    question: str
    answer: str | None = None
    verdict: Verdict | None = None
    score: int | None = None
    judgement: JudgementOut | None = None
    answered_at: datetime | None = None
    created_at: datetime


class InterviewEvaluationOut(BaseModel):
    score: int
    headline: str
    description: str
    stats: list[dict] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class InterviewSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: str
    status: SessionStatus
    asked_count: int
    max_questions: int
    overall_score: int | None = None
    summary: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class InterviewSessionDetailOut(InterviewSessionOut):
    turns: list[InterviewTurnOut] = Field(default_factory=list)
    current_question: CurrentQuestionOut | None = None
    evaluation: InterviewEvaluationOut | None = None
    covered_competencies: list[str] = Field(default_factory=list)
    remaining_questions: int = 0
    # 非致命问题（如简历要点抽取失败导致降级），前端可提示但不阻塞
    warnings: list[str] = Field(default_factory=list)


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class AnswerResponse(BaseModel):
    judgement: JudgementOut
    next_question: CurrentQuestionOut | None = None
    finished: bool = False
    asked_count: int = 0
    max_questions: int = 0


class InterviewListOut(BaseModel):
    items: list[InterviewSessionOut] = Field(default_factory=list)
    total: int = 0
