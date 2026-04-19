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
        model="gpt-4o-mini",
        input=(
            "Provide a comprehensive summary of the following legal document excerpt. "
            "Focus on key elements including parties involved, main facts, legal issues, relief sought, important dates, and any deadlines or next steps. "
            "Structure the summary in clear, concise bullet points that capture the essence of the document.\n\n"
            f"{chunk}"
        ),
        max_output_tokens=1024,
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
                        model="gpt-4o-mini",
                        input=(
                            "Synthesize the following chunk summaries into a cohesive final summary of the entire legal document. "
                            "Create a comprehensive overview that covers all key aspects from the chunks, including parties, facts, legal issues, relief, dates, and deadlines. "
                            "Organize the final summary in clear, well-structured bullet points that provide a complete picture of the document.\n\n"
                            f"{combined}"
                        ),
                        max_output_tokens=1024,
                        temperature=0,
                    )
                    final_text = _get_response_text(response)
                    if final_text:
                        return final_text
            else:
                response = client.responses.create(
                    model="gpt-4o-mini",
                    input=(
                        "You are a legal assistant. Extract ONLY meaningful and relevant legal information from the document.\n\n"

            "STRICT RULES:\n"
            "- Ignore filler text, repetition, and irrelevant narration\n"
            "- Ignore procedural noise or repeated hearing descriptions unless critical\n"
            "- Focus ONLY on actionable legal insights\n\n"

            "Extract and return ONLY these sections:\n"
            "1. Parties Involved\n"
            "2. Case Type / Nature\n"
            "3. Key Facts (important events only)\n"
            "4. Legal Issues / Charges\n"
            "5. Evidence (only strong/important ones)\n"
            "6. Relief Sought / Purpose\n"
            "7. Important Dates / Deadlines\n"
            "8. Court Observations (only if critical)\n"
            "9. Next Actions (VERY IMPORTANT)\n\n"

            "Output in SHORT bullet points. Do NOT include unnecessary sentences.\n\n"

            f"Document:\n{chunk}"
                    ),
                    max_output_tokens=1024,
                    temperature=0,
                )
                final_text = _get_response_text(response)
                if final_text:
                    return final_text
        except Exception:
            pass

    # Enhanced fallback summarizer when AI is not available
    return _extractive_summary(cleaned)


def _extractive_summary(text: str) -> str:
    """Create a simple extractive summary for legal documents when AI is unavailable."""
    sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if s.strip() and len(s.strip()) > 10]
    
    if len(sentences) <= 3:
        return text[:500] + '...' if len(text) > 500 else text
    
    # Remove duplicates
    unique_sentences = []
    seen = set()
    for sentence in sentences:
        lower = sentence.lower()
        if lower not in seen:
            seen.add(lower)
            unique_sentences.append(sentence)
    
    # Extract key sentences
    summary_sentences = []
    
    # Look for sentences with key legal terms
    key_terms = ['affidavit', 'bail', 'application', 'court', 'deponent', 'facts', 'relief', 'verification', 'deponent', 'sworn', 'solemnly']
    
    for sentence in unique_sentences[:15]:  # Check first 15 sentences
        if any(term in sentence.lower() for term in key_terms):
            summary_sentences.append(sentence)
            if len(summary_sentences) >= 6:
                break
    
    # If not enough, add more sentences
    if len(summary_sentences) < 4:
        for sentence in unique_sentences:
            if sentence not in summary_sentences and len(' '.join(summary_sentences + [sentence])) < 800:
                summary_sentences.append(sentence)
                if len(summary_sentences) >= 6:
                    break
    
    summary = '\n'.join(f'• {sentence}' for sentence in summary_sentences[:6])  # Format as bullet points
    
    # Add truncation if still too long
    if len(summary) > 1000:
        summary = summary[:997] + '...'
    
    return summary

