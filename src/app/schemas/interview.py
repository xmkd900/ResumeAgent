from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimType = Literal["project", "experience", "skill", "metric"]
QuestionSource = Literal["resume", "bank", "jd", "generated"]
QuestionType = Literal["concept", "scenario", "project", "behavioral"]
Difficulty = Literal["junior", "mid", "senior"]
SessionStatus = Literal["ongoing", "finished", "aborted"]
MessageRole = Literal["interviewer", "candidate", "system"]
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


class QuestionPlanSlot(BaseModel):
    """一场面试中的一道题；bank_id 与 claim_id 至少有一个用于溯源。"""

    index: int = Field(ge=1)
    source: QuestionSource
    bank_id: int | None = None
    claim_id: int | None = None
    competency: str
    question: str
    evidence_quote: str | None = None
    expected_points: list[str] = Field(default_factory=list)
    rubric: dict = Field(default_factory=dict)
    max_depth: int = Field(default=2, ge=0, le=5)


class QuestionPlan(BaseModel):
    version: int = 1
    slots: list[QuestionPlanSlot]


class InterviewCreateRequest(BaseModel):
    position: str = Field(min_length=1, max_length=64)
    resume_id: int | None = None
    jd_id: int | None = None


class InterviewSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: str
    status: SessionStatus
    total_questions: int
    current_index: int
    current_depth: int
    overall_score: int | None = None
    summary: str | None = None
    question_plan: QuestionPlan | None = None
    started_at: datetime
    finished_at: datetime | None = None


class JudgementOut(BaseModel):
    verdict: Verdict
    hit_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    feedback: str = ""


class CurrentQuestionOut(BaseModel):
    index: int
    total: int
    depth: int
    max_depth: int
    content: str
    competency: str
    source: QuestionSource


class InterviewMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    round: int
    role: MessageRole
    content: str
    question_id: int | None = None
    parent_message_id: int | None = None
    depth: int
    judgement: JudgementOut | None = None
    created_at: datetime


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class AnswerResponse(BaseModel):
    judgement: JudgementOut
    next_question: CurrentQuestionOut | None = None
    finished: bool = False
