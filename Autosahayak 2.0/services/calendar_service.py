import os
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage


def build_ics_invite(
    uid: str,
    summary: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    organizer: str,
    attendee: str,
    location: str | None = None,
) -> bytes:
    start = start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end = end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    location_line = f"LOCATION:{location}\r\n" if location else ""

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "PRODID:-//Autosahayak 2.0//EN\r\n"
        "VERSION:2.0\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VTIMEZONE\r\n"
        "TZID:UTC\r\n"
        "BEGIN:STANDARD\r\n"
        "DTSTART:19700101T000000\r\n"
        "TZOFFSETFROM:+0000\r\n"
        "TZOFFSETTO:+0000\r\n"
        "END:STANDARD\r\n"
        "END:VTIMEZONE\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{dtstamp}\r\n"
        f"DTSTART:{start}\r\n"
        f"DTEND:{end}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"ORGANIZER:mailto:{organizer}\r\n"
        f"ATTENDEE;CN=Lawyer;ROLE=REQ-PARTICIPANT:mailto:{attendee}\r\n"
        f"{location_line}"
        "SEQUENCE:0\r\n"
        "STATUS:CONFIRMED\r\n"
        "TRANSP:OPAQUE\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics.encode("utf-8")


def send_calendar_invite(
    recipient_email: str,
    subject: str,
    body: str,
    start_dt: datetime,
    duration_minutes: int = 60,
    location: str | None = None,
) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("EMAIL_FROM", smtp_user or "no-reply@autosahayak.local")
    if not smtp_host or not smtp_user or not smtp_pass:
        return False

    end_dt = start_dt + timedelta(minutes=duration_minutes)
    uid = str(uuid.uuid4())
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = recipient_email
    message.set_content(body)

    ics_bytes = build_ics_invite(
        uid=uid,
        summary=subject,
        description=body,
        start_dt=start_dt,
        end_dt=end_dt,
        organizer=from_email,
        attendee=recipient_email,
        location=location,
    )

    message.add_attachment(
        ics_bytes,
        maintype="text",
        subtype="calendar",
        filename="invite.ics",
        params={"method": "REQUEST"},
    )

    if smtp_port == 465:
        smtp_class = smtplib.SMTP_SSL
    else:
        smtp_class = smtplib.SMTP

    with smtp_class(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        if smtp_port != 465:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(message)

    return True