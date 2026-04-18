from services.openai_service import get_optional_client


def summarize_text(text: str) -> str:
    client = get_optional_client()
    if client:
        try:
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=f"Summarize this legal text in 4 concise bullet-style sentences:\n\n{text}",
            )
            return response.output_text
        except Exception:
            pass

    cleaned = " ".join(text.split())
    if len(cleaned) <= 220:
        return cleaned
    return f"{cleaned[:217]}..."

