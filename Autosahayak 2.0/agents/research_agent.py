from services.openai_service import get_optional_client
from agents.summarizer_agent import summarize_text


def generate_research_notes(case) -> str:
    """Generate research notes by analyzing case documents and related information."""

    # Collect all relevant case information
    case_info = _collect_case_information(case)

    # Analyze documents if available
    document_analysis = _analyze_case_documents(case)

    # Generate research notes based on analysis
    research_notes = _generate_research_from_analysis(case, case_info, document_analysis)

    return research_notes


def _collect_case_information(case):
    """Collect basic case information for research."""
    return {
        'case_number': case.case_number,
        'court_name': case.court_name,
        'case_type': case.case_type,
        'parties': case.parties_involved,
        'client_name': case.client_name,
        'client_email': case.client_email,
        'created_at': case.created_at.isoformat() if case.created_at else 'Unknown'
    }


def _analyze_case_documents(case):
    """Analyze all documents associated with the case."""
    if not hasattr(case, 'documents') or not case.documents:
        return "No documents available for analysis."

    document_summaries = []
    document_types = {}

    for doc in case.documents:
        # Summarize each document
        summary = summarize_text(doc.content)
        document_summaries.append({
            'type': doc.document_type,
            'summary': summary,
            'created_at': doc.created_at.isoformat() if doc.created_at else 'Unknown'
        })

        # Count document types
        if doc.document_type in document_types:
            document_types[doc.document_type] += 1
        else:
            document_types[doc.document_type] = 1

    # Analyze hearing information if available
    hearing_analysis = _analyze_hearing_history(case)

    return {
        'document_summaries': document_summaries,
        'document_types': document_types,
        'hearing_analysis': hearing_analysis,
        'total_documents': len(case.documents)
    }


def _analyze_hearing_history(case):
    """Analyze hearing history and patterns."""
    if not hasattr(case, 'hearings') or not case.hearings:
        return "No hearing history available."

    hearings = sorted(case.hearings, key=lambda h: h.hearing_date)

    analysis = {
        'total_hearings': len(hearings),
        'upcoming_hearings': [],
        'past_hearings': [],
        'common_actions': {},
        'hearing_frequency': 'Unknown'
    }

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for hearing in hearings:
        hearing_info = {
            'date': hearing.hearing_date.isoformat(),
            'notes': hearing.notes[:200] + '...' if len(hearing.notes) > 200 else hearing.notes,
            'next_action': hearing.next_action
        }

        if hearing.hearing_date >= now:
            analysis['upcoming_hearings'].append(hearing_info)
        else:
            analysis['past_hearings'].append(hearing_info)

        # Track common next actions
        action = hearing.next_action
        if action in analysis['common_actions']:
            analysis['common_actions'][action] += 1
        else:
            analysis['common_actions'][action] = 1

    # Calculate hearing frequency
    if len(hearings) > 1:
        date_diff = (hearings[-1].hearing_date - hearings[0].hearing_date).days
        if date_diff > 0:
            analysis['hearing_frequency'] = f"Approximately every {date_diff / (len(hearings) - 1):.1f} days"

    return analysis


def _generate_research_from_analysis(case, case_info, document_analysis):
    """Generate comprehensive research notes based on case analysis."""

    client = get_optional_client()

    if client:
        try:
            # Use AI to generate research notes
            prompt = _build_research_prompt(case_info, document_analysis)
            response = client.responses.create(
                model="gpt-4o-mini",
                input=prompt,
                max_output_tokens=1500,
                temperature=0.1,
            )

            from agents.summarizer_agent import _get_response_text
            ai_research = _get_response_text(response)
            if ai_research:
                return ai_research
        except Exception:
            pass

    # Fallback to structured analysis
    return _generate_structured_research(case_info, document_analysis)


def _build_research_prompt(case_info, document_analysis):
    """Build a comprehensive research prompt for AI analysis."""

    prompt = f"""You are a legal research assistant. Analyze the following case information and generate comprehensive research notes.

CASE INFORMATION:
- Case Number: {case_info['case_number']}
- Court: {case_info['court_name']}
- Case Type: {case_info['case_type']}
- Parties Involved: {case_info['parties']}
- Client: {case_info['client_name']}

DOCUMENT ANALYSIS:
"""

    if isinstance(document_analysis, dict) and 'document_summaries' in document_analysis:
        for i, doc in enumerate(document_analysis['document_summaries'][:5], 1):  # Limit to 5 docs
            prompt += f"{i}. {doc['type']}: {doc['summary'][:300]}...\n"

        prompt += f"\nDocument Types Summary: {document_analysis.get('document_types', {})}\n"
        prompt += f"Total Documents: {document_analysis.get('total_documents', 0)}\n"

        if 'hearing_analysis' in document_analysis:
            hearing = document_analysis['hearing_analysis']
            prompt += f"\nHEARING ANALYSIS:\n"
            prompt += f"- Total Hearings: {hearing.get('total_hearings', 0)}\n"
            prompt += f"- Hearing Frequency: {hearing.get('hearing_frequency', 'Unknown')}\n"
            if hearing.get('common_actions'):
                prompt += f"- Common Next Actions: {', '.join(list(hearing['common_actions'].keys())[:3])}\n"

    prompt += """

Based on this analysis, generate comprehensive research notes that include:

1. CASE SUMMARY - Brief overview of the case based on documents
2. KEY LEGAL ISSUES - Main legal questions or disputes identified
3. RELEVANT PRECEDENTS - Suggest similar cases or legal principles that may apply
4. EVIDENCE ANALYSIS - Summary of key evidence from documents
5. STRATEGIC RECOMMENDATIONS - Suggested legal strategies based on the analysis
6. POTENTIAL RISKS - Any risks or challenges identified
7. NEXT STEPS - Recommended immediate actions

Format the response in clear sections with bullet points where appropriate. Focus on actionable legal insights."""

    return prompt


def _generate_structured_research(case_info, document_analysis):
    """Generate structured research notes when AI is not available."""

    research = f"""LEGAL RESEARCH NOTES - Case {case_info['case_number']}

================================================================================

CASE OVERVIEW:
• Court: {case_info['court_name']}
• Case Type: {case_info['case_type']}
• Parties: {case_info['parties']}
• Client: {case_info['client_name']}
• Filed: {case_info['created_at']}

================================================================================

DOCUMENT ANALYSIS:
"""

    if isinstance(document_analysis, dict):
        if 'document_types' in document_analysis:
            research += "DOCUMENT TYPES FOUND:\n"
            for doc_type, count in document_analysis['document_types'].items():
                research += f"• {doc_type}: {count} document(s)\n"

        if 'document_summaries' in document_analysis:
            research += "\nKEY DOCUMENT SUMMARIES:\n"
            for doc in document_analysis['document_summaries'][:3]:  # Show top 3
                research += f"• {doc['type']}: {doc['summary'][:200]}...\n"

        if 'hearing_analysis' in document_analysis:
            hearing = document_analysis['hearing_analysis']
            research += f"\nHEARING ANALYSIS:\n"
            research += f"• Total Hearings: {hearing.get('total_hearings', 0)}\n"
            research += f"• Hearing Frequency: {hearing.get('hearing_frequency', 'Unknown')}\n"
            research += f"• Upcoming Hearings: {len(hearing.get('upcoming_hearings', []))}\n"

    research += """

================================================================================

RESEARCH RECOMMENDATIONS:

LEGAL ISSUES TO INVESTIGATE:
• Review relevant case law for similar {case_type} matters
• Analyze procedural compliance and timelines
• Identify potential defenses or counter-arguments

STRATEGIC CONSIDERATIONS:
• Document collection and preservation
• Witness preparation and evidence gathering
• Settlement possibilities and negotiation strategies

NEXT STEPS:
• Conduct detailed legal research on precedents
• Prepare comprehensive case analysis memorandum
• Schedule client consultation for strategy discussion

================================================================================

Note: This is an automated analysis. Please review and supplement with additional research as needed.
"""

    return research.strip()

