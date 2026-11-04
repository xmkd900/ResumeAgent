from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import settings

ALLOWED_MAGIC = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}


@dataclass
class SavedFile:
    path: Path
    size: int
    filename: str


async def save_upload(file: UploadFile, user_id: int) -> SavedFile:
    """落盘上传文件：不信任文件名与 Content-Type，分块写入并校验魔数。"""
    original_name = Path(file.filename or "").name[:255]
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_MAGIC:
        raise HTTPException(status_code=415, detail="只支持 PDF 或 DOCX 文件")

    target_dir = Path(settings.UPLOAD_DIR).resolve() / str(user_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{ext}"
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = 0

    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件不能超过 {settings.MAX_UPLOAD_MB} MB",
                    )
                out.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")

        with target.open("rb") as fh:
            if not fh.read(8).startswith(ALLOWED_MAGIC[ext]):
                raise HTTPException(status_code=415, detail="文件内容与扩展名不匹配")
    except Exception:
        target.unlink(missing_ok=True)
        raise

    return SavedFile(path=target, size=size, filename=original_name or target.name)
