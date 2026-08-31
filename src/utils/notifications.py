"""Notification Dispatcher for Telegram and Gmail (SMTP)."""

from __future__ import annotations

import os
import random
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import requests

from src.utils.logger import logger, console

# Ensure .env is always discovered and loaded dynamically
for _candidate_env in [
    Path(__file__).resolve().parent.parent.parent / ".env",
    Path.cwd() / ".env",
]:
    if _candidate_env.exists():
        load_dotenv(_candidate_env, override=False)


def clean_env_value(val: Optional[str]) -> str:
    """
    Clean and sanitize environment variable values.
    Strips trailing inline comments (e.g. 'token # comment' -> 'token'),
    surrounding quotes (single and double), and leading/trailing whitespace.
    """
    if not val:
        return ""
    val_str = str(val).strip()
    if " #" in val_str:
        val_str = val_str.split(" #", 1)[0].strip()
    elif "\t#" in val_str:
        val_str = val_str.split("\t#", 1)[0].strip()
    return val_str.strip('"').strip("'").strip()


class NotificationService:
    """Dispatches notifications to Telegram and Email (Gmail SMTP) with exponential backoff retries."""

    def __init__(self) -> None:
        # Telegram Settings
        raw_tok = clean_env_value(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        if raw_tok.lower().startswith("bot"):
            raw_tok = raw_tok[3:]
        self.telegram_token = raw_tok
        self.telegram_chat_id = clean_env_value(os.environ.get("TELEGRAM_CHAT_ID", ""))

        # SMTP (Gmail) Settings
        self.smtp_user = clean_env_value(os.environ.get("SMTP_USER", "") or os.environ.get("GMAIL_IMAP_USER", "") or os.environ.get("IMAP_USER", ""))
        self.smtp_password = clean_env_value(os.environ.get("SMTP_PASSWORD", "") or os.environ.get("GMAIL_IMAP_PASSWORD", "") or os.environ.get("IMAP_PASSWORD", ""))
        self.notification_email = clean_env_value(os.environ.get("NOTIFICATION_EMAIL", self.smtp_user))
        self.smtp_host = clean_env_value(os.environ.get("SMTP_HOST", "smtp.gmail.com"))
        raw_port = clean_env_value(os.environ.get("SMTP_PORT", "587"))
        self.smtp_port = int(raw_port) if raw_port.isdigit() else 587

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.notification_email)

    def send_telegram(
        self,
        text: str,
        parse_mode: Optional[str] = "HTML",
        max_retries: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 20.0,
        backoff_factor: float = 2.0,
    ) -> bool:
        """
        Send a message via Telegram Bot API with exponential backoff, randomized jitter,
        and fallback to plain text if HTML parsing fails.
        """
        if not self.telegram_enabled:
            logger.debug("Telegram notifications not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing).")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        current_parse_mode = parse_mode
        current_text = text

        for attempt in range(1, max_retries + 1):
            payload: Dict[str, Any] = {
                "chat_id": self.telegram_chat_id,
                "text": current_text,
                "disable_web_page_preview": False,
            }
            if current_parse_mode:
                payload["parse_mode"] = current_parse_mode

            try:
                resp = requests.post(url, json=payload, timeout=20)

                if resp.status_code == 200:
                    logger.info(f"Telegram notification delivered successfully (attempt {attempt}).")
                    return True

                # If HTML parsing failed (400 Bad Request), fallback immediately to plain text
                if resp.status_code == 400 and current_parse_mode:
                    logger.warning(
                        "Telegram returned 400 Bad Request (likely malformed HTML entity). "
                        "Stripping HTML tags and retrying as plain text..."
                    )
                    current_parse_mode = None
                    current_text = re.sub(r"<[^>]+>", "", text)
                    continue

                # If 404 Not Found, the Bot Token is invalid / rejected by Telegram API (permanent failure)
                if resp.status_code == 404:
                    logger.error(
                        f"Telegram API returned HTTP 404 Not Found ({resp.text.strip()[:150]}). "
                        "The configured TELEGRAM_BOT_TOKEN is invalid or unrecognized by Telegram. "
                        "Aborting retries."
                    )
                    return False

                # Parse response for rate limit retry_after
                retry_after_delay = None
                try:
                    resp_json = resp.json()
                    if "parameters" in resp_json and "retry_after" in resp_json["parameters"]:
                        retry_after_delay = float(resp_json["parameters"]["retry_after"])
                except Exception:
                    pass

                # Transient errors to retry: 429 (rate limit), 500, 502, 503, 504
                if resp.status_code in [429, 500, 502, 503, 504]:
                    logger.warning(
                        f"Telegram API returned HTTP {resp.status_code} ({resp.text.strip()[:150]}) "
                        f"(attempt {attempt}/{max_retries})."
                    )
                else:
                    logger.error(f"Telegram notification permanent failure (Status {resp.status_code}): {resp.text}")
                    return False

            except (requests.exceptions.RequestException, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f"Telegram notification network error ({type(e).__name__}: {e}) (attempt {attempt}/{max_retries}).")

            if attempt < max_retries:
                if retry_after_delay is not None:
                    delay = retry_after_delay + 0.5
                else:
                    delay = min(max_delay, base_delay * (backoff_factor ** (attempt - 1)))
                jitter = random.uniform(0.85, 1.15)
                total_sleep = round(delay * jitter, 2)
                logger.info(f"Retrying Telegram delivery in {total_sleep}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(total_sleep)

        logger.error(f"Failed to deliver Telegram notification after {max_retries} attempts.")
        return False

    def send_email(
        self,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> bool:
        """Send an email notification via Gmail SMTP with retry backoff."""
        if not self.email_enabled:
            logger.debug("Email notifications not configured (SMTP_USER or SMTP_PASSWORD missing).")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Career Engine <{self.smtp_user}>"
        msg["To"] = self.notification_email

        # Attach plain text and HTML versions
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        for attempt in range(1, max_retries + 1):
            try:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=25) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.smtp_user, [self.notification_email], msg.as_string())
                logger.info(f"Email notification delivered to {self.notification_email} (attempt {attempt}).")
                return True
            except Exception as e:
                logger.warning(f"SMTP delivery attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    time.sleep(base_delay * attempt)

        logger.error(f"Failed to send email notification via SMTP after {max_retries} attempts.")
        return False

    def notify_pipeline_run(
        self,
        tenant_name: str,
        total_discovered: int,
        new_jobs: int,
        queued_count: int,
        staged_packages: int,
        warnings: Optional[List[str]] = None
    ) -> None:
        """Send summary notification at the end of a pipeline run including any non-fatal warnings."""
        if not (self.telegram_enabled or self.email_enabled):
            return

        warnings_list = warnings or []
        warning_tag = " [⚠️ Alerts]" if warnings_list else ""
        subject = f"🎯 Career Engine Sourcing Report: {new_jobs} New Jobs | {queued_count} Queued{warning_tag}"

        # Plain text formatting
        warning_text = ""
        if warnings_list:
            warning_text = "\n⚠️ Channel Alerts / Warnings:\n" + "\n".join(f"• {w}" for w in warnings_list) + "\n"

        text_summary = (
            f"Career Engine Sourcing & Scoring Complete\n"
            f"-----------------------------------------\n"
            f"Tenant: {tenant_name}\n"
            f"Total Opportunities Scraped: {total_discovered}\n"
            f"New Job Postings: {new_jobs}\n"
            f"High-Fit Jobs Queued: {queued_count}\n"
            f"Staged Application Packages in /inbox/: {staged_packages}\n"
            f"{warning_text}\n"
            f"Review packages locally or run: python run.py list-inbox"
        )

        # Telegram HTML formatting
        tg_warnings = ""
        if warnings_list:
            formatted_w = "\n".join(f"• <i>{w}</i>" for w in warnings_list)
            tg_warnings = f"\n⚠️ <b>Channel Alerts & Fallbacks:</b>\n{formatted_w}\n"

        tg_html = (
            f"🚀 <b>Career Engine Pipeline Summary</b>\n\n"
            f"👤 <b>Tenant:</b> {tenant_name}\n"
            f"🔍 <b>Listings Scraped:</b> {total_discovered}\n"
            f"✨ <b>New Opportunities:</b> {new_jobs}\n"
            f"🎯 <b>High-Fit Jobs Queued:</b> {queued_count}\n"
            f"📁 <b>Staged Packages:</b> {staged_packages}\n"
            f"{tg_warnings}\n"
            f"<i>Check your /inbox/ directory for generated CV and Cover Letter PDFs!</i>"
        )

        # HTML Email formatting
        html_warning_box = ""
        if warnings_list:
            items_html = "".join(f"<li style='margin-bottom: 4px;'>{w}</li>" for w in warnings_list)
            html_warning_box = f"""
            <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 15px 0; border-radius: 4px; color: #856404; font-size: 13px;">
                <strong>⚠️ Channel Alerts &amp; Fallback Status:</strong>
                <ul style="margin: 6px 0 0 0; padding-left: 20px;">
                    {items_html}
                </ul>
            </div>
            """

        html_email = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                <h2 style="color: #0b57d0; border-bottom: 2px solid #0b57d0; padding-bottom: 8px;">🎯 Career Engine Pipeline Report</h2>
                <p>Hello <strong>{tenant_name}</strong>,</p>
                <p>Your autonomous career sourcing pipeline has executed successfully.</p>
                {html_warning_box}
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Total Scraped</strong></td>
                        <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right;">{total_discovered}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>New Opportunities</strong></td>
                        <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">{new_jobs}</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>High-Fit Queued</strong></td>
                        <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #0b57d0; font-weight: bold;">{queued_count}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Staged Packages in /inbox/</strong></td>
                        <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; font-weight: bold;">{staged_packages}</td>
                    </tr>
                </table>
                <p style="background-color: #e8f0fe; padding: 12px; border-radius: 6px; color: #174ea6;">
                    💡 <strong>Next Step:</strong> Review staged markdown and PDF resumes in <code>~/Portfolio/career-engine/inbox/</code> before approving.
                </p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
                <p style="font-size: 12px; color: #777;">Career Engine Autonomous Orchestrator • Host: vsmlnx</p>
            </div>
        </body>
        </html>
        """

        if self.telegram_enabled:
            self.send_telegram(tg_html, parse_mode="HTML")

        if self.email_enabled:
            self.send_email(subject=subject, body_text=text_summary, body_html=html_email)
