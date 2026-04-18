from services.openai_service import get_optional_client

MAX_SUMMARY_INPUT_CHARS = 3800


def _chunk_text(text: str, size: int) -> list[str]:
    chunks = []
    buffer = []
    current_len = 0
    for word in text.split():
        if current_len + len(word) + 1 > size and buffer:
            chunks.append(" ".join(buffer))
            buffer = []
            current_len = 0
        buffer.append(word)
        current_len += len(word) + 1
    if buffer:
        chunks.append(" ".join(buffer))
    return chunks


def _get_response_text(response) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text.strip()
    if hasattr(response, "output") and response.output:
        try:
            return " ".join(
                part.get("text", "")
                for item in response.output
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            ).strip()
        except Exception:
            pass
    return ""


def _summarize_chunk(client, chunk: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=(
            "Summarize the following legal document excerpt in 6 clear bullet points. "
            "Include the main parties, key facts, relief sought, and any next actions or deadlines.\n\n"
            f"{chunk}"
        ),
        max_output_tokens=512,
        temperature=0,
    )
    return _get_response_text(response)


def summarize_text(text: str) -> str:
    client = get_optional_client()
    cleaned = " ".join(text.split())
    if client:
        try:
            if len(cleaned) > MAX_SUMMARY_INPUT_CHARS:
                chunk_summaries = []
                for chunk in _chunk_text(cleaned, MAX_SUMMARY_INPUT_CHARS):
                    chunk_summary = _summarize_chunk(client, chunk)
                    if chunk_summary:
                        chunk_summaries.append(chunk_summary)
                if chunk_summaries:
                    combined = "\n\n".join(chunk_summaries)
                    response = client.responses.create(
                        model="gpt-4.1-mini",
                        input=(
                            "Combine the following chunk summaries into a final summary with 6 clear bullet points. "
                            "Make sure the final summary covers the full document and highlights the most important legal facts, parties, relief requested, and next steps.\n\n"
                            f"{combined}"
                        ),
                        max_output_tokens=512,
                        temperature=0,
                    )
                    final_text = _get_response_text(response)
                    if final_text:
                        return final_text
            else:
                response = client.responses.create(
                    model="gpt-4.1-mini",
                    input=(
                        "Summarize the following legal text in 6 clear bullet points. "
                        "Include the main parties, key facts, relief sought, and next actions or deadlines.\n\n"
                        f"{cleaned}"
                    ),
                    max_output_tokens=512,
                    temperature=0,
                )
                final_text = _get_response_text(response)
                if final_text:
                    return final_text
        except Exception:
            pass

    if len(cleaned) <= 300:
        return cleaned
    return f"{cleaned[:297]}..."

