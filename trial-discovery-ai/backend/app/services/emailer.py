from __future__ import annotations

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


def send_password_reset_code(
    *,
    recipient_email: str,
    reset_code: str,
    expires_minutes: int,
) -> None:
    settings = get_settings()
    sender = (settings.auth_email_sender or "").strip()
    if not sender:
        raise EmailDeliveryError(
            "AUTH_EMAIL_SENDER is not configured; cannot deliver reset codes by email."
        )

    region = (settings.auth_email_region or settings.s3_region or "us-east-1").strip()
    ses = boto3.client("ses", region_name=region)

    subject = "Acquittify Password Reset Code"
    text_body = (
        "You requested a password reset for your Acquittify account.\n\n"
        f"Reset code: {reset_code}\n"
        f"This code expires in {expires_minutes} minutes.\n\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = (
        "<html><body>"
        "<p>You requested a password reset for your Acquittify account.</p>"
        f"<p><strong>Reset code:</strong> {reset_code}</p>"
        f"<p>This code expires in {expires_minutes} minutes.</p>"
        "<p>If you did not request this, you can ignore this email.</p>"
        "</body></html>"
    )

    try:
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            },
        )
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Failed to send password reset email")
        raise EmailDeliveryError("Failed to deliver password reset email") from exc
