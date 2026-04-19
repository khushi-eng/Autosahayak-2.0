import re

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


def _normalize_document_type(
    document_type: str,
    *,
    facts: str | None = None,
    demand: str | None = None,
    additional_notes: str | None = None,
) -> str:
    combined = " ".join(part.lower() for part in [facts, demand, additional_notes] if part)
    if "affidavit" in combined:
        return "affidavit"
    if "legal notice" in combined or "legal_notice" in combined:
        return "legal_notice"
    if "written statement" in combined or "written_statement" in combined:
        return "written_statement"
    if "complaint" in combined:
        return "complaint"
    if "application" in combined or "bail application" in combined:
        return "application" if document_type != "affidavit" else document_type
    return document_type


def _extract_affidavit_context(
    case: Case,
    *,
    client_name: str | None,
    facts: str | None,
    demand: str | None,
    authority: str | None,
) -> dict[str, str]:
    facts_text = (facts or "").strip()
    lower_facts = facts_text.lower()

    inferred_name = client_name or case.client_name
    name_match = re.search(r"(?:for|of)\s+([a-zA-Z ]+?)(?:\s+age\b|,|\n|$)", facts_text, re.IGNORECASE)
    if name_match:
        candidate = " ".join(name_match.group(1).split())
        if len(candidate.split()) >= 2:
            inferred_name = candidate.title()

    age_match = re.search(r"\bage\s+(\d{1,3})\b", facts_text, re.IGNORECASE)
    age_text = f", aged about {age_match.group(1)} years" if age_match else ""

    place_match = re.search(r"\bage\s+\d{1,3}\s+([a-zA-Z ]+?)(?:\n|,|$)", facts_text, re.IGNORECASE)
    if not place_match:
        place_match = re.search(r"\b(?:resident of|residing at|from)\s+([a-zA-Z ]+?)(?:\n|,|$)", facts_text, re.IGNORECASE)
    place_text = f", resident of {' '.join(place_match.group(1).split()).title()}" if place_match else ""

    inferred_case_type = case.case_type
    if "criminal" in lower_facts:
        inferred_case_type = "Criminal Case"
    elif "civil" in lower_facts:
        inferred_case_type = "Civil Case"

    inferred_authority = authority or case.court_name
    if "bail" in lower_facts and inferred_authority == case.court_name:
        inferred_authority = "The Competent Criminal Court at Pune"

    inferred_demand = demand or ""
    if not inferred_demand and "bail" in lower_facts:
        inferred_demand = f"That bail be granted to {inferred_name} in accordance with law."
    if not inferred_demand:
        inferred_demand = "That appropriate relief be granted in accordance with law."

    return {
        "deponent_name": inferred_name,
        "deponent_description": f"{inferred_name}{age_text}{place_text}",
        "case_type": inferred_case_type,
        "authority": inferred_authority,
        "demand": inferred_demand,
        "facts": facts_text or "Detailed supporting facts will be inserted after client review.",
        "is_bail": "bail" in lower_facts,
    }


def _build_affidavit_fallback(
    case: Case,
    *,
    client_name: str,
    facts: str,
    authority: str,
    demand: str,
    additional_notes: str,
) -> str:
    affidavit_context = _extract_affidavit_context(
        case,
        client_name=client_name,
        facts=facts,
        demand=demand,
        authority=authority,
    )
    demand_block = affidavit_context["demand"]
    notes_block = additional_notes or "No additional instructions were provided."
    title = "AFFIDAVIT IN SUPPORT OF BAIL APPLICATION" if affidavit_context["is_bail"] else "AFFIDAVIT"
    return f"""
{title}

IN THE COURT OF {affidavit_context["authority"].upper()}

I, {affidavit_context["deponent_description"]}, do hereby solemnly affirm and state as under:

1. That I am the deponent in the present matter and I am fully acquainted with the facts and circumstances of the case.
2. That this affidavit is being filed in connection with the present proceedings concerning {affidavit_context["case_type"].lower()}.
3. That the facts stated in the accompanying application/petition are true and correct to my knowledge and belief.
4. That the documents relied upon and filed along with the application are true copies of their respective originals, to the best of my knowledge and belief.
5. That the factual background and relevant case details are as follows:
   {affidavit_context["facts"]}
6. That the relief sought in the matter is as follows:
   {demand_block}
7. That this affidavit is made bona fide and in the interest of justice.

Verification

I, {affidavit_context["deponent_description"]}, the above named deponent, do hereby verify that the contents of paragraphs 1 to 7 above are true and correct to my knowledge and belief, and nothing material has been concealed therefrom.

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
    document_type = _normalize_document_type(
        document_type,
        facts=facts,
        demand=demand,
        additional_notes=additional_notes,
    )
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
            affidavit_context = None
            if document_type == "affidavit":
                affidavit_context = _extract_affidavit_context(
                    case,
                    client_name=client_name,
                    facts=facts,
                    demand=demand,
                    authority=authority,
                )
            
            # Build the prompt with all available information
            prompt_parts = [
                f"Generate a complete {doc_label} for the following legal case:",
                f"Case Type: {(affidavit_context['case_type'] if affidavit_context else case.case_type)}",
                f"Client: {(affidavit_context['deponent_name'] if affidavit_context else (client_name or case.client_name))}",
                f"Client Email: {case.client_email}",
                f"Authority/Court: {(affidavit_context['authority'] if affidavit_context else (authority or case.court_name))}",
            ]
            if document_type != "affidavit":
                prompt_parts.insert(2, f"Case Number: {case.case_number}")
                prompt_parts.append(f"Parties Involved: {case.parties_involved}")
            else:
                prompt_parts.append(
                    "Stored case metadata may be unrelated to this affidavit request. "
                    "Prioritize the deponent details and matter description provided in the user prompt over the open case record."
                )
            
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
            demand=demand or "",
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
