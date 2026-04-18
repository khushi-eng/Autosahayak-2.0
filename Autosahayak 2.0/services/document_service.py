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


def delete_upload_file(file_path: str | None) -> None:
    if not file_path:
        return

    target_path = Path(file_path)
    if target_path.exists() and target_path.is_file():
        target_path.unlink()

