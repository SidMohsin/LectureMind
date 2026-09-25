"""
Notification provider abstraction for sending OTPs via email or SMS.

In development (ENV=development), messages are printed to the console.
In production, plug in a real provider via environment variables:
  EMAIL_PROVIDER=smtp
  SMS_PROVIDER=twilio
"""
import logging
from app.config import settings

logger = logging.getLogger("lecturemind.notifications")


class NotificationError(Exception):
    pass


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(to: str, subject: str, body: str) -> None:
    """Send an email using the configured provider."""
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "console":
        _send_email_console(to, subject, body)
    elif provider == "smtp":
        _send_email_smtp(to, subject, body)
    else:
        raise NotificationError(f"Unknown EMAIL_PROVIDER: '{provider}'. Use 'console' or 'smtp'.")


def _send_email_console(to: str, subject: str, body: str) -> None:
    """Development mode: print email to console."""
    logger.info(
        f"\n{'='*60}\n"
        f"[DEV EMAIL] To: {to}\n"
        f"Subject: {subject}\n"
        f"{'─'*60}\n"
        f"{body}\n"
        f"{'='*60}"
    )
    print(
        f"\n{'='*60}\n"
        f"[DEV EMAIL] To: {to}\n"
        f"Subject: {subject}\n"
        f"{'─'*60}\n"
        f"{body}\n"
        f"{'='*60}"
    )


def _send_email_smtp(to: str, subject: str, body: str) -> None:
    """Send email via SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not settings.SMTP_HOST:
        raise NotificationError("SMTP_HOST is not configured. Set it in your .env file.")

    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, to, msg.as_string())
    except Exception as e:
        logger.error(f"SMTP email failed: {e}")
        raise NotificationError(f"Failed to send email: {e}") from e


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

def send_sms(to: str, body: str) -> None:
    """Send an SMS using the configured provider."""
    provider = settings.SMS_PROVIDER.lower()

    if provider == "console":
        _send_sms_console(to, body)
    elif provider == "twilio":
        _send_sms_twilio(to, body)
    else:
        raise NotificationError(f"Unknown SMS_PROVIDER: '{provider}'. Use 'console' or 'twilio'.")


def _send_sms_twilio(to: str, body: str) -> None:
    """Send an OTP using Twilio's Messages API without adding an SDK dependency."""
    import requests

    account_sid = settings.SMS_API_KEY.strip()
    auth_token = settings.SMS_API_SECRET.strip()
    from_number = settings.SMS_FROM.strip()
    if not all((account_sid, auth_token, from_number)):
        raise NotificationError(
            "Twilio is not configured. Set SMS_API_KEY (Account SID), "
            "SMS_API_SECRET (Auth Token), and SMS_FROM in your .env file."
        )

    try:
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            auth=(account_sid, auth_token),
            data={"To": to, "From": from_number, "Body": body},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise NotificationError("Could not reach Twilio to send the verification code.") from exc

    if response.status_code not in (200, 201):
        try:
            detail = response.json().get("message", "Unknown Twilio error")
        except ValueError:
            detail = response.text[:200]
        raise NotificationError(f"Twilio could not send the verification code: {detail}")


def _send_sms_console(to: str, body: str) -> None:
    """Development mode: print SMS to console."""
    logger.info(
        f"\n{'='*60}\n"
        f"[DEV SMS] To: {to}\n"
        f"{'─'*60}\n"
        f"{body}\n"
        f"{'='*60}"
    )
    print(
        f"\n{'='*60}\n"
        f"[DEV SMS] To: {to}\n"
        f"{'─'*60}\n"
        f"{body}\n"
        f"{'='*60}"
    )


# ---------------------------------------------------------------------------
# Convenience: send OTP
# ---------------------------------------------------------------------------

def send_otp(otp: str, method: str, destination: str) -> None:
    """
    Send an OTP to the user via the chosen method.
    method: 'email' or 'phone'
    destination: email address or phone number
    """
    message = (
        f"Your LectureMind verification code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
        f"Do not share this code with anyone."
    )

    if method == "email":
        send_email(
            to=destination,
            subject=f"LectureMind — Verification Code: {otp}",
            body=message,
        )
    elif method == "phone":
        send_sms(to=destination, body=message)
    else:
        raise NotificationError(f"Unknown OTP method: '{method}'. Use 'email' or 'phone'.")
