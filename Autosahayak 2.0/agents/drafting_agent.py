from database.models import Case
from services.openai_service import get_optional_client


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


def generate_legal_draft(
    document_type: str,
    case: Case,
    *,
    client_name: str | None = None,
    opponent_name: str | None = None,
    facts: str | None = None,
    demand: str | None = None,
    authority: str | None = None,
    additional_notes: str | None = None,
) -> str:
    client = get_optional_client()
    if client:
        try:
            # Map document types to more descriptive labels
            doc_type_labels = {
                "written_statement": "Written Statement",
                "complaint": "Complaint",
                "legal_notice": "Legal Notice",
                "affidavit": "Affidavit",
                "application": "Application"
            }
            
            doc_label = doc_type_labels.get(document_type, document_type.replace("_", " ").title())
            
            # Build the prompt with all available information
            prompt_parts = [
                f"Generate a complete {doc_label} for the following legal case:",
                f"Case Type: {case.case_type}",
                f"Case Number: {case.case_number}",
                f"Client: {client_name or case.client_name}",
                f"Client Email: {case.client_email}",
                f"Parties Involved: {case.parties_involved}",
                f"Authority/Court: {authority or case.court_name}",
            ]
            
            if opponent_name:
                prompt_parts.append(f"Opposite Party: {opponent_name}")
            
            if facts:
                prompt_parts.append(f"Facts: {facts}")
            
            if demand:
                prompt_parts.append(f"Relief/Demand: {demand}")
            
            if additional_notes:
                prompt_parts.append(f"Additional Instructions: {additional_notes}")
            
            prompt = "\n".join(prompt_parts)
            prompt += "\n\nGenerate a properly formatted legal document that includes all necessary sections, proper legal language, and follows standard legal document structure for this type of pleading."
            
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=prompt,
                max_output_tokens=2048,
                temperature=0.1,
            )
            
            generated_text = _get_response_text(response)
            if generated_text:
                return generated_text
        except Exception as e:
            print(f"AI drafting failed: {e}")
    
    # Fallback to basic template if AI is not available
    header = document_type.replace("_", " ").title()
    client = client_name or case.client_name
    authority_name = authority or case.court_name
    opponent = opponent_name or "To be specified"
    facts_block = facts or "Detailed facts will be inserted after client review."
    demand_block = demand or "Appropriate relief may be granted in the interest of justice."
    notes_block = additional_notes or "No additional drafting notes were provided."

    return f"""
{header}

IN THE COURT OF {authority_name.upper()}
Case Number: {case.case_number}
Case Type: {case.case_type}

Parties Involved:
{case.parties_involved}

Client:
{client}
Contact:
{case.client_email}

Opponent:
{opponent}

Facts:
{facts_block}

This {header.lower()} is prepared for the above matter and captures the current case profile for filing and review.

Prayer:
{demand_block}

Drafting Notes:
{notes_block}
""".strip()
