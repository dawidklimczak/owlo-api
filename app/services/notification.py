import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings


logger = logging.getLogger(__name__)


async def send_magic_link(email: str, token: str) -> None:
    """Send magic link email for authentication."""
    link = f"{settings.APP_URL}/auth/verify?token={token}"
    subject = "Your PulseFeed login link"
    html = f"""
    <p>Click the link below to log in to PulseFeed:</p>
    <p><a href="{link}">Log in to PulseFeed</a></p>
    <p>This link expires in {settings.MAGIC_LINK_EXPIRE_MINUTES} minutes.</p>
    <p>If you did not request this, you can safely ignore this email.</p>
    """
    await _send_email(to=email, subject=subject, html=html)


async def send_new_facts_notification(
    email: str,
    topic_title: str,
    new_facts_count: int,
    topic_id: str,
    language: str = "en",
) -> None:
    """Send notification about new facts discovered for a topic."""
    topic_url = f"{settings.APP_URL}/topics/{topic_id}"
    subject = f"New updates: {topic_title}"
    html = f"""
    <p>We found <strong>{new_facts_count} new update(s)</strong> for your tracked topic:</p>
    <p><strong>{topic_title}</strong></p>
    <p><a href="{topic_url}">View updates</a></p>
    """
    await _send_email(to=email, subject=subject, html=html)


async def _send_email(to: str, subject: str, html: str) -> None:
    if settings.EMAIL_PROVIDER == "resend":
        await _send_via_resend(to=to, subject=subject, html=html)
    else:
        await _send_via_smtp(to=to, subject=subject, html=html)


async def _send_via_resend(to: str, subject: str, html: str) -> None:
    import resend

    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send(
        {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )
    logger.info("Email sent via Resend to %s", to)


async def _send_via_smtp(to: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, to, msg.as_string())

    logger.info("Email sent via SMTP to %s", to)
