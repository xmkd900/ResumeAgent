import json
import logging
import re
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Resume

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """文件无法解析时抛出，消息会写入 resume.parse_error。"""


def normalize(text: str) -> str:
    """统一空白但保留段落边界：压缩连续空行，不删除全部换行。"""
    text = text.replace("\u00a0", " ").replace("\u3000", " ").replace("\u200b", "")
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if line:
            lines.append(line)
        elif lines and lines[-1] != "":
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _extract_pdf_page(page: object) -> str:
    """优先用 layout 模式：部分 PDF 的普通文本流会把标题全部排到正文末尾。"""
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except (TypeError, ValueError):  # 老版本 pypdf 不支持 layout
        return page.extract_text() or ""


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ParseError("PDF 已加密，无法提取文本")
    # 页与页之间留空行，避免上一页末行和下一页标题粘在一起
    return "\n\n".join(_extract_pdf_page(page) for page in reader.pages)


def _iter_docx_blocks(document: Document) -> Iterator[Paragraph | Table]:
    """按文档正文顺序产出段落/表格；不能分开遍历，否则表格内容会整体错位到最后一节。"""
    if hasattr(document, "iter_inner_content"):
        yield from document.iter_inner_content()
        return

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _read_docx(path: Path) -> str:
    document = Document(str(path))
    parts: list[str] = []
    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            if block.text.strip():
                parts.append(block.text)
            continue

        # 表格里经常放教育/项目/技能，按行转成文本，保持它在文档中的位置
        for row in block.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _friendly_parse_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "stream has ended" in message or "eof marker" in message:
        return "PDF 文件不完整或已损坏"
    if "not a zip file" in message or "package not found" in message:
        return "DOCX 文件结构无效"
    if "encrypt" in message:
        return "文件已加密，无法提取文本"
    return "文件解析失败，请确认文件未损坏"


def parse_file(path: str) -> tuple[str, dict]:
    file_path = Path(path)
    if not file_path.exists():
        raise ParseError("文件不存在或已被移动")

    ext = file_path.suffix.lower()
    try:
        if ext == ".pdf":
            text = _read_pdf(file_path)
        elif ext == ".docx":
            text = _read_docx(file_path)
        else:
            raise ParseError("不支持的文件类型")
    except ParseError:
        raise
    except Exception as exc:  # 损坏、加密、非标准包结构等
        logger.warning("parse file failed: %s", exc)
        raise ParseError(_friendly_parse_error(exc)) from exc

    text = normalize(text)
    if len(text) < 50:
        raise ParseError("未提取到有效文本，可能是扫描件或加密文件")

    return text, split_sections(text)


SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": (
        "教育",
        "教育背景",
        "教育经历",
        "学习经历",
        "教育程度",
        "学历",
        "education",
        "education background",
        "educationbackground",
        "educational background",
        "educationalbackground",
    ),
    "experience": (
        "实习",
        "实习经历",
        "实习经验",
        "工作经历",
        "工作经验",
        "职业经历",
        "工作履历",
        "实践经历",
        "internship",
        "internship experience",
        "internshipexperience",
        "work experience",
        "workexperience",
        "professional experience",
        "professionalexperience",
    ),
    "projects": (
        "项目",
        "项目经历",
        "项目经验",
        "项目实践",
        "projects",
        "project experience",
        "projectexperience",
    ),
    "skills": (
        "技能",
        "专业技能",
        "技能清单",
        "技术栈",
        "个人技能",
        "技能特长",
        "skills",
        "technical skills",
        "technicalskills",
    ),
    "awards": (
        "获奖",
        "获奖情况",
        "荣誉",
        "荣誉奖项",
        "奖项",
        "证书",
        "资格证书",
        "awards",
        "honors",
        "certificates",
    ),
}

# 用于识别“标题 + 英文副标题”的情况，例如「教育经历 EDUCATION」
ENGLISH_HEADING_LABELS = {
    "EDUCATION",
    "WORK EXPERIENCE",
    "EXPERIENCE",
    "INTERNSHIP",
    "PROJECTS",
    "PROJECT EXPERIENCE",
    "SKILLS",
    "TECHNICAL SKILLS",
    "AWARDS",
    "HONORS",
    "CERTIFICATES",
}

# 未列入别名的常见板块（自我评价、个人信息等）也应切断上一节，避免污染
GENERIC_HEADING_SUFFIXES = (
    "经历",
    "经验",
    "背景",
    "技能",
    "证书",
    "评价",
    "总结",
    "信息",
    "奖项",
    "荣誉",
    "情况",
    "意向",
    "能力",
    "优势",
)

# 允许标题带有限定词，例如「互联网实习经历」「校园项目经历」
HEADING_QUALIFIERS = (
    "互联网",
    "校园",
    "校内",
    "校外",
    "科研",
    "公司",
    "企业",
    "项目",
    "实习",
    "工作",
    "教育",
    "专业",
    "个人",
    "荣誉",
    "竞赛",
    "核心",
    "主要",
    "相关",
    "社会实践",
)

_ALIAS_TO_KEY = {
    re.sub(r"\s+", "", alias).lower(): key
    for key, aliases in SECTION_ALIASES.items()
    for alias in aliases
}
_COMPACT_ALIASES = [
    (key, re.sub(r"\s+", "", alias).lower())
    for key, aliases in SECTION_ALIASES.items()
    for alias in aliases
]


def _strip_heading_decoration(line: str) -> str:
    """去掉序号、项目符号、括号/方括号等装饰，只保留标题候选。"""
    text = re.sub(r"[【】\[\]]", "", line.strip())
    # 中文序号：一、 / （二） / 三.
    text = re.sub(r"^[（(]?[一二三四五六七八九十百]+[）)、.．]\s*", "", text)
    # 阿拉伯数字序号：1. / 1、 / （1）；限制 1-2 位，避免把 2022.09 当成序号
    text = re.sub(r"^[（(]?\d{1,2}[）)、.．]\s*", "", text)
    text = re.sub(r"^[•·◆●○▪◦]\s*", "", text)
    text = re.sub(r"^[-*]\s+", "", text)
    return text.strip(" 　:：-—|·")


def _clean_inline_content(content: str) -> str:
    content = re.sub(r"^[|｜·\-—:：\s】\]]+", "", content).strip()
    if content.upper() in ENGLISH_HEADING_LABELS:
        return ""
    return content


def _looks_like_generic_heading(text: str) -> bool:
    if not text or len(text) > 12:
        return False
    if re.search(r"[A-Za-z0-9]", text):
        return False
    if re.search(r"[，,。；;！？!?、]", text):
        return False
    return text.endswith(GENERIC_HEADING_SUFFIXES)


def _match_heading_text(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text).lower()
    key = _ALIAS_TO_KEY.get(compact)
    if key:
        return key

    # 「互联网实习经历」「校园项目经历」：别名 + 限定词前缀
    for key, alias in _COMPACT_ALIASES:
        if len(alias) < 4 or not compact.endswith(alias) or len(compact) <= len(alias):
            continue
        prefix = compact[: -len(alias)]
        if any(prefix.endswith(qualifier) for qualifier in HEADING_QUALIFIERS):
            return key
    return None


def _match_heading(line: str) -> tuple[str | None, str]:
    """返回 (section_key, 标题行内正文)。key 为 None 表示不是标题。"""
    candidate = _strip_heading_decoration(line)
    if not candidate:
        return None, ""

    key = _match_heading_text(candidate)
    if key:
        return key, ""

    # 标题带括号补充：教育经历（本科）、项目经历（独立负责）
    bracket = re.match(r"^(.+?)[（(](.+?)[）)]\s*$", candidate)
    if bracket:
        key = _match_heading_text(bracket.group(1).strip())
        if key:
            return key, _clean_inline_content(bracket.group(2))

    # 标题 + 冒号 + 行内正文，例如「技能：Java、MySQL」
    parts = re.split(r"[:：]", candidate, maxsplit=1)
    head = parts[0].strip()
    key = _match_heading_text(head)
    if key:
        content = _clean_inline_content(parts[1]) if len(parts) > 1 else ""
        return key, content

    # 标题 + 空格 + 行内正文，例如「项目经历 校园平台」
    if " " in candidate:
        head, rest = candidate.split(" ", 1)
        key = _match_heading_text(head.strip())
        if key:
            return key, _clean_inline_content(rest)
        if _looks_like_generic_heading(head.strip()):
            return "other", _clean_inline_content(rest)

    # 未知但形态像标题的行（如「自我评价」「个人信息」）切到 other，不能混进上一节
    if _looks_like_generic_heading(head):
        content = _clean_inline_content(parts[1]) if len(parts) > 1 else ""
        return "other", content

    return None, ""


def split_sections(text: str) -> dict[str, list[str]]:
    """按板块切分简历：保留标题行内正文，未知板块归入 other，不丢正文。"""
    sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
    sections["other"] = []
    current = "other"

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        key, inline_content = _match_heading(stripped)
        if key is not None:
            current = key
            if inline_content:
                sections[current].append(inline_content)
            continue

        sections[current].append(stripped)
    print("切分结果:", json.dumps(sections, ensure_ascii=False, indent=2))

    return sections


def _mark_failed(resume_id: int, session_factory: Callable, reason: str) -> None:
    db = None
    try:
        db = session_factory()
        resume = db.get(Resume, resume_id)
        if resume is None or resume.parse_status == "done":
            return
        resume.parse_status = "failed"
        resume.parse_error = reason[:250]
        db.commit()
    except Exception:
        logger.exception("failed to mark resume %s as failed", resume_id)
    finally:
        if db is not None:
            db.close()


def parse_resume_task(resume_id: int, session_factory: Callable = SessionLocal) -> None:
    """后台解析任务：独立 Session；任何异常都必须落成 failed，不能留下永久 pending。"""
    db = None
    try:
        db = session_factory()
        resume = db.get(Resume, resume_id)
        if resume is None:
            logger.warning("parse task: resume %s not found", resume_id)
            return
        if resume.parse_status == "done":
            logger.info("parse task: resume %s already parsed, skip", resume_id)
            return

        try:
            text, sections = parse_file(resume.file_path)
            resume.raw_text = text
            resume.sections = sections
            resume.parse_status = "done"
            resume.parse_error = None
        except Exception as exc:  # noqa: BLE001  解析异常类型多，统一落库为 failed
            logger.warning("parse resume %s failed: %s", resume_id, exc)
            resume.parse_status = "failed"
            resume.parse_error = str(exc)[:250]

        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("persist parse result failed for resume %s", resume_id)
            _mark_failed(resume_id, session_factory, "解析结果写入失败，请重试")
    except Exception:
        logger.exception("parse task crashed for resume %s", resume_id)
        _mark_failed(resume_id, session_factory, "解析任务异常中断，请重试")
    finally:
        if db is not None:
            db.close()


def recover_stale_pending(
    session_factory: Callable = SessionLocal, older_than_minutes: int = 10
) -> int:
    """服务重启/任务丢失后，把超时的 pending 标记为 failed，允许用户手动重试。"""
    db = None
    try:
        db = session_factory()
        cutoff = datetime.now() - timedelta(minutes=older_than_minutes)
        stale = db.scalars(
            select(Resume).where(Resume.parse_status == "pending", Resume.created_at < cutoff)
        ).all()
        for resume in stale:
            resume.parse_status = "failed"
            resume.parse_error = "解析任务已中断（服务重启或超时），请点击重新解析"
        if stale:
            db.commit()
        return len(stale)
    except Exception:
        logger.exception("recover stale pending resumes failed")
        return 0
    finally:
        if db is not None:
            db.close()
