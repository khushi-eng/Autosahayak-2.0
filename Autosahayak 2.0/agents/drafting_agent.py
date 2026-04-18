from database.models import Case


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
