import os

from utils.logging_config import get_logger


logger = get_logger(__name__)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


def has_openai_client() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") and OpenAI is not None)


def get_optional_client():
    if not has_openai_client():
        return None
    try:
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception as exc:  # pragma: no cover
        logger.warning("Falling back to mocked AI response: %s", exc)
        return None

