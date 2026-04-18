from datetime import datetime, timedelta


def detect_due_deadlines(deadlines):
    now = datetime.utcnow()
    threshold = now + timedelta(hours=24)
    return [deadline for deadline in deadlines if now <= deadline.deadline <= threshold]


def trigger_reminder(title: str, recipient: str, deadline: datetime) -> str:
    message = f"[Reminder] Deadline '{title}' is due on {deadline.isoformat()} for {recipient}."
    print(message)
    return message

