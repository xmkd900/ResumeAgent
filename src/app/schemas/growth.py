from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.interview import JudgementOut

WeakSource = Literal["interview", "self_test"]
WeakSeverity = Literal["low", "medium", "high"]
WeakStatus = Literal["open", "fixed", "resolved"]


class WeakPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    domain: str = ""
    source: WeakSource
    severity: WeakSeverity
    relapse_count: int = 0
    mastery_score: int = 0
    resolved: bool = False
    related_tags: list[str] = Field(default_factory=list)
    last_evidence: str | None = None
    last_session_id: int | None = None
    practice_count: int = 0
    last_practiced_at: datetime | None = None
    # v2：缺口修复与复习排期
    source_turn_id: int | None = None
    gap_point: str | None = None
    gap_quote: str | None = None
    status: WeakStatus = "open"
    review_stage: int = 0
    interval_days: int = 0
    ease_factor: float = 2.5
    next_review_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    fix_count: int = 0
    review_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    @field_validator("related_tags", mode="before")
    @classmethod
    def _none_tags_to_list(cls, value):
        return value or []


class WeakPointStatsOut(BaseModel):
    active: int = 0
    avg_mastery: int = 0
    weekly_practices: int = 0
    high_priority: int = 0


class WeakPointListOut(BaseModel):
    items: list[WeakPointOut] = Field(default_factory=list)
    stats: WeakPointStatsOut = Field(default_factory=WeakPointStatsOut)
    total: int = 0


class ExerciseSourceOut(BaseModel):
    idx: int
    title: str
    meta: str = ""


class PracticeContentOut(BaseModel):
    """练习视图的"先讲清楚"部分。

    intro 里的 [n] 只能来自 sources，服务层会校验编号范围。
    """

    intro: list[str] = Field(default_factory=list)
    question: str = ""
    sources: list[ExerciseSourceOut] = Field(default_factory=list)


class ExerciseOut(BaseModel):
    question_id: int | None = None
    title: str
    type: str = "概念讲解"
    difficulty: str = "mid"
    minutes: int = 8
    tags: list[str] = Field(default_factory=list)
    reason: str = ""


class WeakPointExercisesOut(BaseModel):
    weak_point: WeakPointOut
    content: PracticeContentOut
    exercises: list[ExerciseOut] = Field(default_factory=list)


class PracticeRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    # 为 null 表示使用自拟的复述题（题库没有匹配题时）
    question_id: int | None = None


class PracticeResultOut(BaseModel):
    judgement: JudgementOut
    mastery_before: int
    mastery_after: int
    resolved: bool
    hint: str = ""
    weak_point: WeakPointOut


class QueueStatsOut(BaseModel):
    open: int = 0
    due: int = 0
    resolved: int = 0


class WeakPointQueueOut(BaseModel):
    """今日队列：待修复 + 今日到期复查。"""

    stats: QueueStatsOut = Field(default_factory=QueueStatsOut)
    fix: list[WeakPointOut] = Field(default_factory=list)
    review: list[WeakPointOut] = Field(default_factory=list)
    next_review_at: datetime | None = None


class  GapSourceOut(BaseModel):
    """缺口卡里的"原题 + 原话"，用于回放上下文。"""

    session_id: int | None = None
    turn_id: int | None = None
    turn_index: int | None = None
    question: str = ""
    answer: str = ""
    quote: str = ""


class ReviewQuestionOut(BaseModel):
    question_id: int | None = None
    title: str = ""
    type: str = "概念讲解"
    difficulty: str = "mid"
    # bank 题库原题 / rewritten 由原题改写的变体题（无 id，不落题库）
    origin: str = "bank"
    reason: str = ""


class GapCardOut(BaseModel):
    weak_point: WeakPointOut
    source: GapSourceOut = Field(default_factory=GapSourceOut)
    suggestion: str = ""
    # Fix 的题面：页面展示的就是判卷时用的那段文字
    fix_prompt: str = ""
    review_question: ReviewQuestionOut | None = None


class FixRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


class FixResultOut(BaseModel):
    judgement: JudgementOut
    gap_covered: bool
    weak_point: WeakPointOut
    before_answer: str = ""
    after_answer: str = ""
    message: str = ""


class ReviewRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    question_id: int | None = None


class ReviewResultOut(BaseModel):
    question: str
    judgement: JudgementOut
    gap_covered: bool
    weak_point: WeakPointOut
    message: str = ""
