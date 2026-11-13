"""面试官（director）：每一轮根据对话决定问什么。

与旧实现的区别：
- 不预生成整卷，因此不会出现"第 4 题才自我介绍"这种顺序错误；
- 题库是工具：需要结构化题目时调 `search_bank`，不需要时按简历/JD 现场出题；
- 追问深度、题目数量由模型结合回答质量决定，代码只保留预算与去重等护栏。

每轮只做一次决策，状态全部来自 MySQL，因此进程重启/刷新不会丢上下文。
"""

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.llm.json import extract_json_object
from app.models import InterviewTurn, ResumeClaim
from app.services.interview_context import question_brief

logger = logging.getLogger(__name__)

MAX_FOLLOWUP_DEPTH = 4
MAX_CLAIMS_IN_BRIEFING = 14
MAX_TURNS_RENDERED = 8
MAX_JD_REQUIREMENTS = 8

_ACTION_LABELS = {
    "open": "开场",
    "ask": "提问",
    "followup": "追问",
    "legacy": "历史",
}


class DirectorError(Exception):
    """面试官决策异常。
    
    Attributes:
        status_code: HTTP状态码，默认502
    """
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# 结构化输出
# --------------------------------------------------------------------------- #
class JdRequirement(BaseModel):
    """JD能力要求项。
    
    Attributes:
        text: 要求描述
        kind: 类型（must/nice）
        competency: 能力维度
    """
    text: str = Field(min_length=2, max_length=200)
    kind: str = "must"
    competency: str = ""


class OpeningQuestion(BaseModel):
    """开场问题。
    
    Attributes:
        question: 问题内容
        competency: 能力维度
        expected_points: 期望得分点
    """
    question: str = Field(min_length=6)
    competency: str = "自我介绍"
    expected_points: list[str] = Field(default_factory=list)


class BriefingResult(BaseModel):
    """面试准备结果。
    
    Attributes:
        jd_requirements: JD能力要求列表
        opening: 开场问题
    """
    jd_requirements: list[JdRequirement] = Field(default_factory=list)
    opening: OpeningQuestion


class DirectorDecision(BaseModel):
    """面试官决策结果。

    Attributes:
        action: 动作类型（ask/followup/search_bank/finish）
        followup_kind: 追问类型（verify 验真 / deepen 加深 / clarify 澄清）
        probe_quote: 追问锚定的候选人原话
        reason: 决策原因
        competency: 考察能力项
        anchor: 问题来源（resume/jd/bank/general）
        claim_id: 简历声明ID
        question: 具体问题
        expected_points: 期望得分点
        search_query: 检索词
        search_competency: 检索能力项
        search_difficulty: 检索难度
    """

    action: str = "ask"
    followup_kind: str = "deepen"
    probe_quote: str | None = None
    reason: str = ""
    competency: str = ""
    anchor: str = "general"
    claim_id: int | None = None
    question: str | None = None
    expected_points: list[str] = Field(default_factory=list)
    search_query: str | None = None
    search_competency: str | None = None
    search_difficulty: str | None = None


class BankChoice(BaseModel):
    """题库选题结果。
    
    Attributes:
        question_id: 题目ID（null表示自拟）
        question: 问题内容
        competency: 能力维度
        expected_points: 期望得分点
        reason: 选择原因
    """
    question_id: int | None = None
    question: str = Field(min_length=6)
    competency: str = ""
    expected_points: list[str] = Field(default_factory=list)
    reason: str = ""


class EvaluationNarrative(BaseModel):
    """评估文案。
    
    Attributes:
        headline: 标题
        description: 描述
        strengths: 优点列表
        improvements: 改进建议列表
    """
    headline: str = ""
    description: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 模型调用与修复
# --------------------------------------------------------------------------- #
def _call_json(
    *,
    system: str,
    user: str,
    model_cls: type[BaseModel],
    label: str,
    max_tokens: int = 1400,
    temperature: float = 0.3,
) -> BaseModel:
    """调用LLM并解析JSON返回，失败重试一次。
    
    Args:
        system: 系统提示词
        user: 用户输入
        model_cls: 返回的Pydantic模型类
        label: 调用标签（用于日志）
        max_tokens: 最大token数
        temperature: 温度参数
    
    Returns:
        解析后的模型对象
    
    Raises:
        DirectorError: LLM不可用或输出格式错误
    """
    if not (settings.LLM_API_KEY or "").strip():
        raise DirectorError("未配置 LLM_API_KEY，无法调用面试官模型", status_code=503)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_error: Exception | None = None

    for attempt in range(2):
        content = ""
        try:
            response = chat(messages, max_tokens=max_tokens, temperature=temperature)
            content = response.content
            return model_cls.model_validate(extract_json_object(content))
        except (ValueError, TypeError, ValidationError) as exc:
            last_error = exc
            logger.warning("%s 输出不合法（第 %s 次）：%s", label, attempt + 1, exc)
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": (content or "{}")[:2000]},
                    {
                        "role": "user",
                        "content": (
                            f"上一次输出不符合要求：{str(exc)[:300]}。"
                            "请只返回符合字段要求的 JSON 对象，不要额外解释。"
                        ),
                    },
                ]
        except LLMError as exc:
            raise DirectorError(str(exc), status_code=exc.status_code) from exc
        except Exception as exc:  # pragma: no cover - 兜底
            logger.exception("%s 调用失败", label)
            raise DirectorError("面试官模型暂时不可用，请稍后重试", 502) from exc

    raise DirectorError(f"{label} 输出格式不符合要求，已重试仍失败", 502) from last_error


def _squash(text: str, limit: int) -> str:
    """文本压缩：去除多余空白并截断。
    
    Args:
        text: 原始文本
        limit: 最大长度
    
    Returns:
        压缩后的文本
    """
    return re.sub(r"\s+", " ", (text or "").strip())[:limit]


# --------------------------------------------------------------------------- #
# 建会话：提炼 JD 能力项 + 写开场
# --------------------------------------------------------------------------- #
BRIEFING_SYSTEM_PROMPT = """你是一名资深技术面试官。你刚拿到候选人的简历和岗位要求，准备开始一场模拟面试。

请做两件事：

1. 从岗位要求中提炼 3-6 条能力要求。能直接从 JD 读到的放 kind="must"；属于加分项的放 kind="nice"。
   每条给一个简短的 competency（2-8 字，技术名词优先，如 MySQL、Redis、系统设计、项目深度、沟通表达）。
   如果 JD 为空，按该岗位的通用核心能力提炼。

2. 写第一句开场提问。
   - 必须让候选人先讲清背景：自我介绍，或讲一段最相关的经历；
   - 如果简历里有明显的主项目，可以点名请他从那个项目讲起；
   - 口语化，1-2 句，只问一件事，不考技术细节。

只输出 JSON：
{
  "jd_requirements": [{"text": "熟悉 MySQL 索引与事务", "kind": "must", "competency": "MySQL"}],
  "opening": {
    "question": "先简单介绍一下你自己，重点讲讲和这个岗位最相关的一段经历吧。",
    "competency": "自我介绍",
    "expected_points": ["一句话定位", "最相关的经历", "与岗位的连接"]
  }
}"""


def build_briefing(
    *,
    position: str,
    jd_text: str | None,
    resume_text: str,
    claims: list[ResumeClaim],
    catalog: list[dict],
    domain: str,
) -> tuple[dict, OpeningQuestion]:
    """构建面试背景快照和开场问题。
    
    Args:
        position: 岗位名称
        jd_text: JD文本
        resume_text: 简历文本
        claims: 简历声明列表
        catalog: 题库能力分布
        domain: 题库领域
    
    Returns:
        (背景快照字典, 开场问题对象)
    """
    claim_lines = [
        f"- #{claim.id} [{claim.claim_type}] {claim.title}"
        f" | 技术: {', '.join(claim.tech_tags or []) or '无'}"
        f" | 证据: {_squash(claim.evidence_quote, 160)}"
        for claim in claims[:MAX_CLAIMS_IN_BRIEFING]
    ]
    user = (
        f"<position>{position}</position>\n"
        f"<jd>\n{_squash(jd_text or '', 2000) or '（未提供）'}\n</jd>\n"
        f"<resume_excerpt>\n{resume_text or '（未解析出文本）'}\n</resume_excerpt>\n"
        f"<resume_claims>\n{chr(10).join(claim_lines) or '（未抽取到结构化要点）'}\n</resume_claims>"
    )

    result = _call_json(
        system=BRIEFING_SYSTEM_PROMPT,
        user=user,
        model_cls=BriefingResult,
        label="面试准备",
        max_tokens=1200,
        temperature=0.3,
    )
    assert isinstance(result, BriefingResult)

    requirements = [
        {
            "text": _squash(item.text, 200),
            "kind": "must" if item.kind != "nice" else "nice",
            "competency": _squash(item.competency, 40) or "综合",
        }
        for item in result.jd_requirements[:MAX_JD_REQUIREMENTS]
    ]

    briefing = {
        "version": 1,
        "domain": domain,
        "position": position,
        "jd_requirements": requirements,
        "catalog": catalog[:40],
        "claims": [
            {
                "id": claim.id,
                "type": claim.claim_type,
                "title": claim.title,
                "tags": list(claim.tech_tags or [])[:8],
                "evidence": _squash(claim.evidence_quote, 160),
            }
            for claim in claims[:MAX_CLAIMS_IN_BRIEFING]
        ],
        "resume_excerpt": _squash(resume_text, 1600),
    }
    return briefing, result.opening


# --------------------------------------------------------------------------- #
# 每轮决策
# --------------------------------------------------------------------------- #
DIRECTOR_SYSTEM_PROMPT = """你是一场技术模拟面试的面试官，正在和候选人实时对话。
你要像真人一样判断：这一句问什么、问多深、什么时候收尾。

## 判断依据
- 简历要点是主线：项目要问透，写了的数字要问来源；
- 岗位要求决定能力覆盖；
- 判卷结果里除了分数，还有三个关键信号：
  · depth：recall 只会复述 / understood 讲得清原理 / applied 有动手细节 / reflective 能反思局限；
  · probe_needed：这段回答里最经不起追问的那一点（probe_target）；
  · hedging：他用了多少"好像是 / 记不清 / 大概"这类模糊限定。
- **只要上一轮 probe_needed=true，这一轮就必须追问验真，不许换话题**——
  这是区分"真做过"和"背过"的唯一办法。只有连续追问到 3 层仍无进展，才允许换方向。
- 题库能力分布告诉你"还有哪些方向可以考"。需要一道结构化题目（八股/场景）时用 search_bank，否则直接按简历/JD 提问。

## 追问三型（followup_kind 必须填）
- verify 验真：揪住他说的具体表述要细节——"这个 QPS 是在什么压测条件下跑出来的？"
- deepen 加深：答对了往下压边界/失败/规模——"如果这时候锁过期了会发生什么？"
- clarify 澄清：答非所问或前后矛盾时，先给一次说清楚的机会。

## 提问原则
1. 第 1 题必须是开场：自我介绍或讲最相关的一段经历，不考八股。
2. 简历优先：挑还没问过的项目，按"背景→职责→技术难点→为什么这么选→怎么验证→出事怎么办"推进，但每次只取一个点。
3. 简历没体现、但岗位要求的能力，用题库补；优先没覆盖过的 competency。
4. 追问必须锚定上一轮回答里的具体词（probe_quote 抄原话）：他说"加了缓存"，就问一致性；
   他说"做了优化"，就问指标怎么测。不要用"具体说说"这种空追问。
5. 一次只问一个问题，口语化，1-3 句。**一句话只能有一个问号**，不要用"另外/同时/以及"再追加第二个小问；
   不要报题型，不要说"这题考察的是"，不要提示答案。
6. 不要重复已问过的问题；除追问外，不要连续两题考同一个 competency。
7. 难度跟着表现走：答得扎实就加压（规模、边界、故障成本）；答得含糊就下钻到具体场景，
   不要在同一个层次换同义词重问一遍。
8. 收尾：核心能力已覆盖、简历项目已问透、或预算用完。宁可少问，不要为凑数硬问。

## expected_points 怎么写
写 2-4 条**可以核对**的答案要素：具体做法、关键取舍、怎么验证、出问题怎么兜。
不要写"了解 XXX""熟悉原理"这种名词短语——如果候选人只要蹦出这个词就算命中，这条要点就写废了。

## 反面例子（不要这样）
上一轮问"订单系统怎么做的"，候选人答"用了 Redis 做缓存，QPS 从 800 提到 3000"。
错误追问："这个 QPS 是在什么压测条件下测的？另外缓存和数据库的一致性怎么保证？"
—— 两个问号，候选人只会挑一个答。
正确追问："QPS 从 800 提到 3000，这个数字是在什么场景下压出来的？"
（一致性留到下一轮再问。）

## 动作
- ask：换一个新话题
- followup：就上一轮回答再追一层（同一 competency）
- search_bank：需要结构化题目，给出检索词
- finish：结束面试

## 输出 JSON
{
  "action": "ask | followup | search_bank | finish",
  "followup_kind": "verify | deepen | clarify",
  "probe_quote": "追问锚定的候选人原话（followup 必填）",
  "reason": "一句话说明为什么现在问这个",
  "competency": "考察的能力项",
  "anchor": "resume | jd | bank | general",
  "claim_id": 12,
  "question": "要问的话（ask/followup 必填）",
  "expected_points": ["可核对的具体做法/取舍/验证方式", "2-4 条"],
  "search_query": "检索词（search_bank 必填）",
  "search_competency": "限定能力项，可空",
  "search_difficulty": "junior | mid | senior，可空"
}"""


def _render_claims(briefing: dict, asked_claim_ids: set[int]) -> str:
    """渲染简历要点，已问过的标记为空，未问过的标记为*。
    
    Args:
        briefing: 面试背景快照
        asked_claim_ids: 已问过的声明ID集合
    
    Returns:
        格式化的简历要点文本
    """
    lines = []
    for claim in briefing.get("claims") or []:
        marker = " " if claim.get("id") in asked_claim_ids else "*"
        tags = "、".join(claim.get("tags") or []) or "无"
        lines.append(
            f"{marker} #{claim.get('id')} [{claim.get('type')}] {claim.get('title')}"
            f" | 技术: {tags} | 证据: {claim.get('evidence')}"
        )
    return "\n".join(lines) or "（无结构化简历要点）"


def _render_jd(briefing: dict) -> str:
    """渲染JD要求列表。
    
    Args:
        briefing: 面试背景快照
    
    Returns:
        格式化的JD要求文本
    """
    lines = [
        f"- ({item.get('kind')}) {item.get('text')} [{item.get('competency')}]"
        for item in briefing.get("jd_requirements") or []
    ]
    return "\n".join(lines) or "（未提供 JD，按岗位通用要求提问）"


def _render_catalog(briefing: dict, covered: set[str]) -> str:
    """渲染题库能力分布，已覆盖的标记✓。
    
    Args:
        briefing: 面试背景快照
        covered: 已覆盖的能力维度集合
    
    Returns:
        格式化的题库分布文本
    """
    parts = []
    for item in briefing.get("catalog") or []:
        name = item.get("competency")
        marker = "✓" if name in covered else "·"
        parts.append(f"{marker}{name}({item.get('count')})")
    return " ".join(parts) or "（题库为空，只能按简历/JD 出题）"


def _render_turns(turns: list[InterviewTurn]) -> str:
    """渲染最近8轮问答记录。

    Args:
        turns: 所有回合列表

    Returns:
        格式化的问答记录文本
    """
    visible = turns[-MAX_TURNS_RENDERED:]
    lines: list[str] = []
    if len(turns) > len(visible):
        lines.append(f"（更早的 {len(turns) - len(visible)} 轮已省略）")

    for turn in visible:
        label = _ACTION_LABELS.get(turn.action, turn.action)
        head = (
            f"{turn.turn_index}. [{label}·{turn.competency or '综合'}]"
            f" 问: {_squash(turn.question, 150)}"
        )
        if turn.answer:
            judged = turn.verdict or "未判"
            detail = ""
            gap = ""
            probe = ""
            hedge = ""
            if isinstance(turn.judgement, dict):
                dims = turn.judgement.get("dimensions") or {}
                if dims:
                    detail = (
                        f"（具体{dims.get('specificity', 0)}/25"
                        f" 推理{dims.get('reasoning', 0)}/25"
                        f" 自证{dims.get('authenticity', 0)}/15）"
                    )
                misses = turn.judgement.get("missing_points") or []
                if misses:
                    gap = "；缺口: " + "、".join(str(item) for item in misses[:3])
                words = turn.judgement.get("hedging") or []
                if words:
                    hedge = "；模糊词: " + "、".join(str(item) for item in words[:4])
                if turn.judgement.get("probe_needed"):
                    probe = str(turn.judgement.get("probe_target") or "").strip()
            head += (
                f"\n   答: {_squash(turn.answer, 200)}"
                f"\n   判卷: {judged}{detail}{gap}{hedge}"
            )
            if probe:
                head += f"\n   待验真: {probe}"
        lines.append(head)
    return "\n".join(lines) or "（还没有提问）"


def _covered_competencies(turns: list[InterviewTurn]) -> set[str]:
    """获取已覆盖的能力维度（只统计open和ask动作）。
    
    Args:
        turns: 所有回合列表
    
    Returns:
        已覆盖的能力维度集合
    """
    return {
        turn.competency
        for turn in turns
        if turn.competency and turn.action in {"open", "ask"}
    }


def _asked_claim_ids(turns: list[InterviewTurn]) -> set[int]:
    """获取已问过的简历声明ID集合。
    
    Args:
        turns: 所有回合列表
    
    Returns:
        已问过的声明ID集合
    """
    return {turn.claim_id for turn in turns if turn.claim_id is not None}


def _pending_probe(turns: list[InterviewTurn]) -> str:
    """上一轮回答里最该验真的那一点；没有就返回空串。

    追问深度到 3 层还没问出来，基本可以判定这块是空的，
    再往下钻只会变成拷问，所以到此为止。
    """
    last_answered = next((turn for turn in reversed(turns) if turn.answer), None)
    if last_answered is None or last_answered.depth >= 3:
        return ""
    judgement = last_answered.judgement or {}
    if not judgement.get("probe_needed"):
        return ""
    return str(judgement.get("probe_target") or "").strip()


def decide(
    *,
    briefing: dict,
    turns: list[InterviewTurn],
    asked_count: int,
    min_questions: int,
    max_questions: int,
    note: str | None = None,
) -> DirectorDecision:
    """让面试官给出这一轮的决策；格式不合法时自动修复一次。
    
    Args:
        briefing: 面试背景快照
        turns: 所有回合列表
        asked_count: 已问轮数
        min_questions: 最小题数
        max_questions: 最大题数
        note: 系统提示（用于重试）
    
    Returns:
        面试官决策对象
    
    Raises:
        DirectorError: 决策失败或格式错误
    """
    covered = _covered_competencies(turns)
    asked_claims = _asked_claim_ids(turns)
    unanswered = [turn for turn in turns if not turn.answer]
    last_answered = next(
        (turn for turn in reversed(turns) if turn.answer), None
    )
    pending_probe = _pending_probe(turns)

    state = (
        f"【岗位】{briefing.get('position') or ''}\n"
        f"【岗位要求】\n{_render_jd(briefing)}\n"
        f"【简历要点】（* 表示还没问到）\n{_render_claims(briefing, asked_claims)}\n"
        f"【题库能力分布】（✓ 已覆盖）\n{_render_catalog(briefing, covered)}\n"
        f"【已问记录】\n{_render_turns(turns)}\n"
        f"【当前进度】已问 {asked_count} 题，其中追问 "
        f"{sum(1 for t in turns if t.action == 'followup')} 次；"
        f"预算 {min_questions}-{max_questions} 题，还可问 {max(0, max_questions - asked_count)} 题\n"
        f"【当前待答】{'有，还没回答' if unanswered else '无'}\n"
        f"【最近一次回答】"
        f"{_squash(last_answered.answer, 300) if last_answered and last_answered.answer else '（无）'}\n"
        f"【待验真】{pending_probe or '无，这段回答没有明显站不住的地方'}\n"
    )
    if note:
        state += f"\n【系统提示】{note}\n"

    current_note = note
    last_error: Exception | None = None

    for attempt in range(2):
        decision = _call_json(
            system=DIRECTOR_SYSTEM_PROMPT,
            user=state + (f"\n【系统提示】{current_note}\n" if current_note and current_note != note else ""),
            model_cls=DirectorDecision,
            label="面试官决策",
            max_tokens=900,
            temperature=0.5,
        )
        assert isinstance(decision, DirectorDecision)

        try:
            decision = _sanitize_decision(
                decision,
                turns=turns,
                asked_count=asked_count,
                min_questions=min_questions,
                max_questions=max_questions,
            )
        except DirectorError as exc:
            if attempt == 0:
                last_error = exc
                current_note = str(exc)
                logger.info("决策被护栏拒绝，带上提示重试：%s", exc)
                continue
            raise

        # 上一轮回答有站不住的表述却想换话题：这是一场面试"变水"的主要出口，先拦一次
        if (
            pending_probe
            and decision.action in {"ask", "search_bank"}
            and attempt == 0
        ):
            current_note = (
                "上一轮回答里有未经证实的表述：" + pending_probe +
                "。请先追问这一点（action=followup，followup_kind=verify），"
                "并在 probe_quote 里抄一句他的原话，不要换话题。"
            )
            last_error = DirectorError(current_note)
            logger.info("面试官想换话题，但上一轮有未验证表述，要求先追问")
            continue

        # 太早收尾时给模型一次机会重新考虑；仍坚持则尊重它的判断
        if (
            decision.action == "finish"
            and asked_count < min_questions
            and attempt == 0
        ):
            current_note = (
                f"现在还不能结束：至少还要问 {min_questions - asked_count} 题，"
                "请继续覆盖简历或岗位能力。"
            )
            last_error = DirectorError(current_note)
            logger.info("模型过早收尾，要求继续提问")
            continue

        logger.info(
            "director decision action=%s competency=%s depth=%s reason=%s",
            decision.action,
            decision.competency,
            "followup" if decision.action == "followup" else "-",
            _squash(decision.reason, 120),
        )
        return decision

    raise DirectorError("面试官没有给出可执行的决策") from last_error


def _sanitize_decision(
    decision: DirectorDecision,
    *,
    turns: list[InterviewTurn],
    asked_count: int,
    min_questions: int,
    max_questions: int,
) -> DirectorDecision:
    """代码护栏：校验决策合法性，防止模型越界。
    
    Args:
        decision: LLM返回的原始决策
        turns: 所有回合列表
        asked_count: 已问轮数
        min_questions: 最小题数
        max_questions: 最大题数
    
    Returns:
        清洗后的决策对象
    
    Raises:
        DirectorError: 决策不合法
    """
    action = (decision.action or "").strip().lower()
    if action not in {"ask", "followup", "search_bank", "finish"}:
        raise DirectorError(f"面试官返回了未知动作：{decision.action}")

    last_answered = next((turn for turn in reversed(turns) if turn.answer), None)

    if action == "followup":
        can_followup = last_answered is not None and last_answered.depth < MAX_FOLLOWUP_DEPTH
        if not can_followup:
            if decision.question:
                logger.info("followup 不可用，降级为 ask")
                action = "ask"
            else:
                raise DirectorError("当前不能再追问，但没有给出新问题")
        elif not (decision.question or "").strip():
            raise DirectorError("追问缺少具体问题")

    if action in {"ask", "followup"} and not (decision.question or "").strip():
        raise DirectorError("决策缺少 question 字段")

    if action == "search_bank" and not (
        (decision.search_query or "").strip() or (decision.search_competency or "").strip()
    ):
        raise DirectorError("检索题缺少 search_query 或 search_competency")

    if asked_count >= max_questions:
        return decision.model_copy(update={"action": "finish", "reason": "已达到题目预算"})

    updates: dict = {"action": action}
    if decision.competency:
        updates["competency"] = _squash(decision.competency, 64)
    if decision.expected_points:
        updates["expected_points"] = [
            _squash(item, 120) for item in decision.expected_points if str(item).strip()
        ][:5]
    kind = (decision.followup_kind or "").strip().lower()
    updates["followup_kind"] = kind if kind in {"verify", "deepen", "clarify"} else "deepen"
    updates["probe_quote"] = _squash(decision.probe_quote or "", 120) or None
    return decision.model_copy(update=updates)


# --------------------------------------------------------------------------- #
# 从题库候选中挑一道并改写
# --------------------------------------------------------------------------- #
BANK_SYSTEM_PROMPT = """你是技术面试官，需要从题库候选里挑一道题，并结合当前对话改写成口头提问。

规则：
1. 只能从给定候选里选，question_id 必须来自候选；
2. 改写可以贴合候选人的项目和上下文，但不能改变考点；
3. 优先选能力项还没被覆盖、难度与当前表现匹配的；
4. 如果所有候选都不合适，question_id 返回 null，自己出一道同 competency 的题；
5. 一次只问一个问题，口语化，1-3 句。

输出 JSON：
{
  "question_id": 12,
  "question": "你项目里用了 Redis，如果缓存和数据库不一致，你会怎么处理？",
  "competency": "Redis",
  "expected_points": ["一致性策略", "失败补偿", "权衡"],
  "reason": "候选覆盖缓存一致性，候选人项目里正好用到"
}"""


def choose_from_bank(
    *,
    briefing: dict,
    turns: list[InterviewTurn],
    decision: DirectorDecision,
    candidates: list,
) -> BankChoice:
    """从题库候选中选择并改写题目。
    
    Args:
        briefing: 面试背景快照
        turns: 所有回合列表
        decision: 面试官决策
        candidates: 题库候选题目列表
    
    Returns:
        选中的题目（可能改写）
    
    Raises:
        DirectorError: 题库为空
    """
    if not candidates:
        raise DirectorError("题库没有可用的候选题")

    payload = [question_brief(question) for question in candidates]
    user = (
        f"【岗位】{briefing.get('position') or ''}\n"
        f"【检索意图】{decision.search_query or ''}\n"
        f"【目标能力】{decision.search_competency or decision.competency or '不限'}\n"
        f"【已经问过】\n{_render_turns(turns[-4:])}\n"
        f"【候选题目】\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    choice = _call_json(
        system=BANK_SYSTEM_PROMPT,
        user=user,
        model_cls=BankChoice,
        label="题库选题",
        max_tokens=800,
        temperature=0.4,
    )
    assert isinstance(choice, BankChoice)

    valid_ids = {question.id for question in candidates}
    if choice.question_id is not None and choice.question_id not in valid_ids:
        logger.warning("模型返回了候选外的 question_id=%s，按自拟题处理", choice.question_id)
        choice = choice.model_copy(update={"question_id": None})
    return choice


# --------------------------------------------------------------------------- #
# 收尾评估
# --------------------------------------------------------------------------- #
EVALUATION_SYSTEM_PROMPT = """你是刚结束一场技术面试的面试官，需要给候选人一份简短、具体、可行动的复盘。

要求：
1. headline 不超过 30 字，点出这场最突出的特征，不要写"表现不错"这类通用话；
2. description 2-3 句，说明整体表现与原因，必须引用具体题目或候选人原话；
3. strengths 2-4 条，只能是这场里确实出现过的表现，并且能指到证据；
   "沟通逻辑清晰""基础扎实"这类没有依据的评价不许写；
4. improvements 2-4 条，必须写成"下一场遇到 X 问题怎么答"，
   禁止"多练习""加强深度""多总结"这种放之四海皆准的空话；
5. 判卷里标了"模糊表述""只有概念没有亲历"的能力项，必须在 improvements 里点名，
   并说明缺的是哪个具体细节（数字来源、取舍理由、失败处理）；
6. 候选人明确承认不会的项，如实写"未掌握"，不要包装成"有待提升"；
7. 不虚构未出现的内容；语气客观，不吹捧也不打击。

输出 JSON：
{"headline": "...", "description": "...", "strengths": ["..."], "improvements": ["..."]}"""


def write_evaluation(
    *,
    position: str,
    turns: list[InterviewTurn],
    score: int,
    covered: list[str],
    dimensions: dict | None = None,
    unanswered: int = 0,
) -> EvaluationNarrative:
    """生成面试评估文案。

    Args:
        position: 岗位名称
        turns: 所有回合列表
        score: 总分
        covered: 覆盖的能力维度列表
        dimensions: 各维度平均得分（用于校准语气与点名短板）
        unanswered: 未作答轮数

    Returns:
        评估文案对象
    """
    lines = []
    for turn in turns:
        if not turn.answer:
            continue
        gaps = ""
        signals = ""
        if isinstance(turn.judgement, dict):
            misses = turn.judgement.get("missing_points") or []
            if misses:
                gaps = "；缺口: " + "、".join(str(item) for item in misses[:3])
            words = turn.judgement.get("hedging") or []
            if words:
                signals += "；模糊表述: " + "、".join(str(item) for item in words[:3])
            if turn.judgement.get("declared_unknown"):
                signals += "；明确表示不会"
            if turn.judgement.get("contradiction") in {"minor", "major"}:
                signals += "；前后不一致"
        lines.append(
            f"{turn.turn_index}. [{turn.competency}] {_squash(turn.question, 100)}\n"
            f"   答: {_squash(turn.answer, 220)}\n"
            f"   判卷: {turn.verdict or '未判'}（{turn.score if turn.score is not None else '-'} 分）{gaps}{signals}"
        )

    dim_lines = ""
    if dimensions:
        labels = {
            "coverage": "要点覆盖",
            "specificity": "具体程度",
            "reasoning": "推理深度",
            "authenticity": "经历自证",
            "clarity": "表达结构",
        }
        dim_lines = "；".join(
            f"{labels.get(key, key)} {value}" for key, value in dimensions.items()
        )

    user = (
        f"【岗位】{position}\n"
        f"【系统计算的总分】{score}/100（只用于校准语气，不要直接复述）\n"
        f"【维度均分】{dim_lines or '无'}\n"
        f"【未作答】{unanswered} 题\n"
        f"【覆盖能力】{'、'.join(covered) or '无'}\n"
        f"【面试记录】\n{chr(10).join(lines) or '（候选人没有作答）'}"
    )
    result = _call_json(
        system=EVALUATION_SYSTEM_PROMPT,
        user=user,
        model_cls=EvaluationNarrative,
        label="面试评估",
        max_tokens=900,
        temperature=0.4,
    )
    assert isinstance(result, EvaluationNarrative)
    return result
