"""Notification Dispatcher for Telegram and Gmail (SMTP)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from src.utils.logger import logger, console


class NotificationService:
    """Dispatches notifications to Telegram and Email (Gmail SMTP)."""

    def __init__(self) -> None:
        # Telegram Settings
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

        # SMTP (Gmail) Settings
        self.smtp_user = os.environ.get("SMTP_USER", "").strip()
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
        self.notification_email = os.environ.get("NOTIFICATION_EMAIL", self.smtp_user).strip()
        self.smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.notification_email)

    def send_telegram(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message via Telegram Bot API."""
        if not self.telegram_enabled:
            logger.debug("Telegram notifications not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing).")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                logger.info("Telegram notification delivered successfully.")
                return True
            else:
                logger.error(f"Telegram notification failed (Status {resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")
            return False

    def send_email(self, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Send an email notification via Gmail SMTP."""
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

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, [self.notification_email], msg.as_string())
            logger.info(f"Email notification delivered to {self.notification_email}.")
            return True
        except Exception as e:
            logger.error(f"Failed to send email notification via SMTP: {e}")
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
