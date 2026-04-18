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


def _build_document_specific_instruction(document_type: str) -> str:
    instructions = {
        "affidavit": (
            "Draft this as a sworn affidavit in first person. Include a title, deponent details, "
            "verification of identity/capacity, numbered paragraphs of facts, a truth-and-correctness "
            "statement, a statement that supporting documents are true/correct where applicable, "
            "a verification clause, place, date, and deponent signature block. "
            "If the matter relates to bail in a criminal case, make the affidavit suitable for supporting a bail application."
        ),
        "application": (
            "Draft this as a formal court application with heading, parties, brief facts, grounds, "
            "prayer clause, and signature block."
        ),
        "complaint": (
            "Draft this as a formal complaint with parties, material facts, cause of action, "
            "relief sought, and verification."
        ),
        "written_statement": (
            "Draft this as a written statement with preliminary submissions, para-wise defence where appropriate, "
            "brief facts, legal position, and prayer."
        ),
        "legal_notice": (
            "Draft this as a legal notice with sender/recipient framing, concise facts, legal assertions, "
            "demand, timeline for compliance, and consequences of non-compliance."
        ),
    }
    return instructions.get(
        document_type,
        "Draft a complete, properly formatted legal document with clear sections, numbered facts, and a prayer/signature block where appropriate.",
    )


def _build_affidavit_fallback(
    case: Case,
    *,
    client_name: str,
    facts: str,
    authority: str,
    demand: str,
    additional_notes: str,
) -> str:
    demand_block = demand or "That the accompanying bail application or related relief be considered in accordance with law."
    notes_block = additional_notes or "No additional instructions were provided."
    return f"""
AFFIDAVIT

IN THE COURT OF {authority.upper()}
Case Number: {case.case_number}
Case Type: {case.case_type}

I, {client_name}, do hereby solemnly affirm and state as under:

1. That I am the deponent in the present matter and I am fully acquainted with the facts and circumstances of the case.
2. That this affidavit is being filed in connection with the present proceedings concerning {case.case_type.lower()}.
3. That the facts stated in the accompanying application/petition are true and correct to my knowledge and belief.
4. That the documents relied upon and filed along with the application are true copies of their respective originals, to the best of my knowledge and belief.
5. That the factual background and relevant case details are as follows:
   {facts}
6. That the relief sought in the matter is as follows:
   {demand_block}
7. That this affidavit is made bona fide and in the interest of justice.

Verification

I, {client_name}, the above named deponent, do hereby verify that the contents of paragraphs 1 to 7 above are true and correct to my knowledge and belief, and nothing material has been concealed therefrom.

Verified at __________________ on ___ / ___ / ______.

Deponent

Additional Notes:
{notes_block}
""".strip()


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
            prompt += (
                "\n\n"
                + _build_document_specific_instruction(document_type)
                + "\nUse the supplied facts to infer the natural legal framing where possible. "
                "If the prompt is short or informal, convert it into formal legal drafting without inventing unsupported facts."
            )
            
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

    if document_type == "affidavit":
        return _build_affidavit_fallback(
            case,
            client_name=client,
            facts=facts_block,
            authority=authority_name,
            demand=demand_block,
            additional_notes=notes_block,
        )

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
