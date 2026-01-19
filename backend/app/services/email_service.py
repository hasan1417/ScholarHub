"""
Email Service for transactional emails.
Uses Mailtrap SMTP in development, Resend API in production.
Handles email verification, password reset, and welcome emails.
"""
import base64
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache the logo base64 data
_logo_base64 = None


def _get_logo_base64() -> str:
    """Get the animated logo as base64 data URL."""
    global _logo_base64
    if _logo_base64 is None:
        logo_path = os.path.join(os.path.dirname(__file__), "..", "static", "logo-animated.gif")
        try:
            with open(logo_path, "rb") as f:
                _logo_base64 = base64.b64encode(f.read()).decode()
        except FileNotFoundError:
            logger.warning(f"Logo file not found: {logo_path}")
            _logo_base64 = ""
    return _logo_base64

# Initialize Resend client lazily
_resend_client = None


def _get_resend():
    """Get or initialize the Resend client."""
    global _resend_client
    if _resend_client is None:
        if not settings.RESEND_API_KEY:
            logger.warning("RESEND_API_KEY not configured. Emails will not be sent.")
            return None
        import resend
        resend.api_key = settings.RESEND_API_KEY
        _resend_client = resend
    return _resend_client


def _send_email_smtp(to: str, subject: str, html: str) -> bool:
    """
    Send an email using SMTP (Mailtrap for development).
    Returns True if successful, False otherwise.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USERNAME:
        logger.warning("SMTP not configured. Email not sent.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL or "noreply@scholarhub.dev"
        msg["To"] = to

        html_part = MIMEText(html, "html")
        msg.attach(html_part)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to], msg.as_string())

        logger.info(f"Email sent via SMTP: {subject} to {to}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {subject} to {to}. Error: {e}")
        return False


def _send_email_resend(to: str, subject: str, html: str) -> bool:
    """
    Send an email using Resend API.
    Returns True if successful, False otherwise.
    """
    resend = _get_resend()
    if resend is None:
        logger.info(f"Email not sent (Resend not configured): {subject} to {to}")
        return False

    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        resend.Emails.send(params)
        logger.info(f"Email sent via Resend: {subject} to {to}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {subject} to {to}. Error: {e}")
        return False


def _send_email(to: str, subject: str, html: str) -> bool:
    """
    Send an email using the appropriate provider.
    - Development: Uses SMTP (Mailtrap)
    - Production: Uses Resend API
    """
    # In development, prefer SMTP (Mailtrap) if configured
    if settings.ENVIRONMENT == "development" and settings.SMTP_HOST:
        return _send_email_smtp(to, subject, html)

    # Fall back to Resend
    return _send_email_resend(to, subject, html)


def send_verification_email(to: str, token: str, name: Optional[str] = None) -> bool:
    """
    Send email verification link to user.
    """
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    greeting = f"Hi {name}," if name else "Hi there,"

    # In development, always log the verification URL for easy access
    if settings.ENVIRONMENT == "development":
        logger.info("=" * 60)
        logger.info(f"[DEV] EMAIL VERIFICATION for {to}")
        logger.info(f"[DEV] Click here to verify: {verification_url}")
        logger.info("=" * 60)

    logo_b64 = _get_logo_base64()
    logo_img = f'<img src="data:image/gif;base64,{logo_b64}" alt="ScholarHub" width="40" height="40" style="vertical-align: middle;" />' if logo_b64 else ''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">
                {logo_img}
                <span style="vertical-align: middle; margin-left: 2px;">ScholarHub</span>
            </h1>
            <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 14px;">Your Research Collaboration Platform</p>
        </div>

        <div style="background: #ffffff; padding: 32px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 16px 16px;">
            <h2 style="color: #1e293b; margin-top: 0;">Verify your email address</h2>

            <p>{greeting}</p>

            <p>Welcome to ScholarHub! Please verify your email address to complete your registration and start collaborating on research.</p>

            <div style="text-align: center; margin: 32px 0;">
                <a href="{verification_url}" style="display: inline-block; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Verify Email Address
                </a>
            </div>

            <p style="color: #64748b; font-size: 14px;">This link will expire in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.</p>

            <p style="color: #64748b; font-size: 14px;">If you didn't create a ScholarHub account, you can safely ignore this email.</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">

            <p style="color: #94a3b8; font-size: 12px; margin-bottom: 0;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <a href="{verification_url}" style="color: #6366f1; word-break: break-all;">{verification_url}</a>
            </p>
        </div>
    </body>
    </html>
    """

    return _send_email(to, "Verify your ScholarHub email", html)


def send_password_reset_email(to: str, token: str, name: Optional[str] = None) -> bool:
    """
    Send password reset link to user.
    """
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    greeting = f"Hi {name}," if name else "Hi there,"

    # In development, always log the reset URL for easy access
    if settings.ENVIRONMENT == "development":
        logger.info("=" * 60)
        logger.info(f"[DEV] PASSWORD RESET for {to}")
        logger.info(f"[DEV] Click here to reset: {reset_url}")
        logger.info("=" * 60)

    logo_b64 = _get_logo_base64()
    logo_img = f'<img src="data:image/gif;base64,{logo_b64}" alt="ScholarHub" width="40" height="40" style="vertical-align: middle;" />' if logo_b64 else ''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">
                {logo_img}
                <span style="vertical-align: middle; margin-left: 2px;">ScholarHub</span>
            </h1>
            <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 14px;">Your Research Collaboration Platform</p>
        </div>

        <div style="background: #ffffff; padding: 32px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 16px 16px;">
            <h2 style="color: #1e293b; margin-top: 0;">Reset your password</h2>

            <p>{greeting}</p>

            <p>We received a request to reset your ScholarHub password. Click the button below to choose a new password.</p>

            <div style="text-align: center; margin: 32px 0;">
                <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Reset Password
                </a>
            </div>

            <p style="color: #64748b; font-size: 14px;">This link will expire in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s).</p>

            <p style="color: #64748b; font-size: 14px;">If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">

            <p style="color: #94a3b8; font-size: 12px; margin-bottom: 0;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <a href="{reset_url}" style="color: #6366f1; word-break: break-all;">{reset_url}</a>
            </p>
        </div>
    </body>
    </html>
    """

    return _send_email(to, "Reset your ScholarHub password", html)


def send_welcome_email(to: str, name: Optional[str] = None) -> bool:
    """
    Send welcome email after successful verification.
    """
    greeting = f"Hi {name}!" if name else "Hi there!"
    projects_url = f"{settings.FRONTEND_URL}/projects"

    logo_b64 = _get_logo_base64()
    logo_img = f'<img src="data:image/gif;base64,{logo_b64}" alt="ScholarHub" width="40" height="40" style="vertical-align: middle;" />' if logo_b64 else ''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">
                {logo_img}
                <span style="vertical-align: middle; margin-left: 2px;">ScholarHub</span>
            </h1>
            <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 14px;">Your Research Collaboration Platform</p>
        </div>

        <div style="background: #ffffff; padding: 32px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 16px 16px;">
            <h2 style="color: #1e293b; margin-top: 0;">Welcome to ScholarHub!</h2>

            <p>{greeting}</p>

            <p>Your email has been verified and your account is ready. Here's what you can do next:</p>

            <ul style="color: #475569; padding-left: 20px;">
                <li style="margin-bottom: 8px;"><strong>Create a research project</strong> to organize your papers and collaborate with your team</li>
                <li style="margin-bottom: 8px;"><strong>Discover relevant papers</strong> using our AI-powered search</li>
                <li style="margin-bottom: 8px;"><strong>Write and collaborate</strong> on documents with real-time editing</li>
                <li style="margin-bottom: 8px;"><strong>Chat with your references</strong> using our AI assistant</li>
            </ul>

            <div style="text-align: center; margin: 32px 0;">
                <a href="{projects_url}" style="display: inline-block; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                    Go to Your Projects
                </a>
            </div>

            <p style="color: #64748b; font-size: 14px;">If you have any questions, feel free to reach out. We're here to help!</p>

            <p style="margin-bottom: 0;">Happy researching,<br><strong>The ScholarHub Team</strong></p>
        </div>
    </body>
    </html>
    """

    return _send_email(to, "Welcome to ScholarHub!", html)
