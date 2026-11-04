import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Resume

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """文件无法解析时抛出，消息会写入 resume.parse_error。"""


def normalize(text: str) -> str:
    """压缩空白但不破坏段落边界。"""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ParseError("PDF 已加密，无法提取文本")
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _read_docx(path: Path) -> str:
    document = Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs]
    # 表格里经常放技能/经历，漏掉会显著影响诊断
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
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


SECTION_PATTERNS = {
    "education": r"^(教育|教育背景|学历)",
    "experience": r"^(实习|工作经历|职业经历)",
    "projects": r"^(项目|项目经历)",
    "skills": r"^(技能|专业技能|技术栈)",
    "awards": r"^(获奖|证书|荣誉)",
}


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_PATTERNS}
    sections["other"] = []
    current = "other"

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for key, pattern in SECTION_PATTERNS.items():
            if re.match(pattern, stripped):
                current = key
                break
        else:
            sections[current].append(stripped)

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
