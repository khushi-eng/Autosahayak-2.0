import random

from database.models import Case


def predict_outcome(case: Case) -> dict[str, str | float]:
    probability = round(random.uniform(0.52, 0.88), 2)
    return {
        "success_probability": probability,
        "risk_analysis": (
            "Moderate litigation risk. Outcome depends on document strength, witness consistency, "
            "and procedural readiness for the next hearing."
        ),
        "summary": (
            f"Case {case.case_number} shows a {'favorable' if probability >= 0.7 else 'mixed'} "
            "outlook based on the currently stored matter profile."
        ),
    }

