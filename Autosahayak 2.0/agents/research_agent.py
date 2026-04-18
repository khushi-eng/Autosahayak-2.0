from database.models import Case


def generate_research_notes(case: Case) -> str:
    return f"""
Research Notes for Case {case.case_number}

Relevant Precedents:
1. State vs. Kumar (2018): Clarified the evidentiary standard for documentary submissions.
2. Rao vs. Union Board (2020): Emphasized procedural fairness and timely notice to all parties.
3. Mehta Infrastructure vs. City Authority (2022): Focused on interim relief where irreparable harm is likely.

Suggested Strategy:
- Reconcile the pleadings with documentary evidence already on file.
- Highlight procedural compliance and client-specific equities.
- Prepare a concise argument note for the next hearing.
""".strip()

