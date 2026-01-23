"""
Shared Email Service

Centralized email sending infrastructure for all automation features.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional, List
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from apps.automation import config

logger = logging.getLogger(__name__)

# Jinja2 template environment
_template_env = None


def get_template_env() -> Environment:
    """Get or create Jinja2 template environment."""
    global _template_env
    if _template_env is None:
        _template_env = Environment(
            loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
            autoescape=True
        )
    return _template_env


def render_template(template_name: str, **context) -> str:
    """Render an HTML template with the given context."""
    env = get_template_env()
    template = env.get_template(template_name)
    return template.render(**context)


def send_email(
    to: str,
    subject: str,
    html_body: str,
    from_name: Optional[str] = None,
    attachments: Optional[List[tuple]] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None
) -> bool:
    """
    Send an HTML email.

    Args:
        to: Recipient email address
        subject: Email subject line
        html_body: HTML content of the email
        from_name: Display name for sender (defaults to config)
        attachments: List of (filename, content, mime_type) tuples
        cc: CC recipient
        bcc: BCC recipient

    Returns:
        True if sent successfully, False otherwise
    """
    if not config.SMTP_ENABLED:
        logger.warning("SMTP is disabled, email not sent")
        return False

    if not config.SMTP_USERNAME or not config.SMTP_PASSWORD:
        logger.error("SMTP credentials not configured")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name or config.EMAIL_FROM_NAME} <{config.SMTP_USERNAME}>"
        msg["To"] = to

        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc

        # Attach HTML body
        msg.attach(MIMEText(html_body, "html"))

        # Attach files if provided
        if attachments:
            for filename, content, mime_type in attachments:
                if isinstance(content, str):
                    content = content.encode('utf-8')

                attachment = MIMEApplication(content, _subtype=mime_type.split('/')[-1])
                attachment.add_header(
                    'Content-Disposition',
                    'attachment',
                    filename=filename
                )
                msg.attach(attachment)

        # Build recipient list
        recipients = [to]
        if cc:
            recipients.append(cc)
        if bcc:
            recipients.append(bcc)

        # Send email
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent successfully to {to}: {subject}")
        return True

    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return False


def send_template_email(
    to: str,
    subject: str,
    template_name: str,
    context: dict,
    **kwargs
) -> bool:
    """
    Send an email using a Jinja2 template.

    Args:
        to: Recipient email address
        subject: Email subject line
        template_name: Name of template file in templates directory
        context: Template context variables
        **kwargs: Additional arguments passed to send_email

    Returns:
        True if sent successfully, False otherwise
    """
    html_body = render_template(template_name, **context)
    return send_email(to, subject, html_body, **kwargs)


# Common email styles for inline HTML
EMAIL_STYLES = """
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }
    .header {
        background: linear-gradient(135deg, #1a365d 0%, #2b6cb0 100%);
        color: white;
        padding: 20px;
        text-align: center;
        border-radius: 8px 8px 0 0;
    }
    .header h1 {
        margin: 0;
        font-size: 24px;
    }
    .header .date {
        opacity: 0.9;
        font-size: 14px;
        margin-top: 5px;
    }
    .content {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-top: none;
        padding: 20px;
        border-radius: 0 0 8px 8px;
    }
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 15px;
        margin: 20px 0;
    }
    .metric-card {
        background: #f8fafc;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #1a365d;
    }
    .metric-label {
        font-size: 12px;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-delta {
        font-size: 12px;
        margin-top: 5px;
    }
    .delta-up { color: #16a34a; }
    .delta-down { color: #dc2626; }
    .delta-neutral { color: #64748b; }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    th, td {
        padding: 10px;
        text-align: left;
        border-bottom: 1px solid #e2e8f0;
    }
    th {
        background: #f1f5f9;
        font-weight: 600;
        font-size: 12px;
        text-transform: uppercase;
        color: #475569;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 500;
    }
    .status-active { background: #dcfce7; color: #166534; }
    .status-pending { background: #fef3c7; color: #92400e; }
    .status-sold { background: #fee2e2; color: #991b1b; }
    .property-card {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        margin: 15px 0;
        overflow: hidden;
    }
    .property-image {
        width: 100%;
        height: 180px;
        object-fit: cover;
        background: #f1f5f9;
    }
    .property-details {
        padding: 15px;
    }
    .property-price {
        font-size: 20px;
        font-weight: 700;
        color: #1a365d;
    }
    .property-address {
        color: #475569;
        margin: 5px 0;
    }
    .property-specs {
        display: flex;
        gap: 15px;
        color: #64748b;
        font-size: 14px;
    }
    .section-title {
        font-size: 18px;
        font-weight: 600;
        color: #1a365d;
        margin: 25px 0 15px 0;
        padding-bottom: 10px;
        border-bottom: 2px solid #e2e8f0;
    }
    .footer {
        text-align: center;
        padding: 20px;
        color: #64748b;
        font-size: 12px;
    }
    .btn {
        display: inline-block;
        padding: 10px 20px;
        background: #1a365d;
        color: white;
        text-decoration: none;
        border-radius: 6px;
        font-weight: 500;
    }
    .btn:hover {
        background: #2b6cb0;
    }
</style>
"""
