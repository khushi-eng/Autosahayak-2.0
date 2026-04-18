from pathlib import Path

from fastapi import UploadFile


UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def save_upload_file(upload: UploadFile | None, prefix: str) -> str | None:
    if upload is None or not upload.filename:
        return None

    safe_name = upload.filename.replace(" ", "_")
    target_path = UPLOAD_DIR / f"{prefix}_{safe_name}"
    content = await upload.read()
    target_path.write_bytes(content)
    return str(target_path)

