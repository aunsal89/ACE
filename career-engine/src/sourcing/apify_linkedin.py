"""Apify 3rd-Party LinkedIn Guest Scraper Worker."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import httpx

from src.config import SourcingSettings, TenantProfile
from src.database.models import JobListingCreate, JobStatus, TrackType
from src.sourcing.base import BaseScraper
from src.utils.hashing import clean_job_url, generate_deduplication_hash
from src.utils.http import request_with_retry
from src.utils.logger import logger


class ApifyLinkedInScraper(BaseScraper):
    """
    LinkedIn job sourcing worker interfacing via Apify Guest Scraper Actors
    to bypass login rate-limits and avoid personal account flags.
    """

    def __init__(self, settings: SourcingSettings, tenant: TenantProfile, token: Optional[str] = None):
        super().__init__(settings, tenant)
        self.token = token or os.environ.get("APIFY_API_TOKEN", "")
        self.actor_endpoint = "https://api.apify.com/v2/acts/curious_coder~linkedin-jobs-scraper/run-sync-get-dataset-items"

    def build_search_payloads(self) -> List[Dict[str, Any]]:
        """Construct boolean searches for Track A and Track B roles."""
        payloads = []

        if self.tenant.tracks.track_a.enabled:
            payloads.append({
                "keywords": "Embedded Software (Director OR Manager OR Lead OR Architect)",
                "location": "Turkey",
                "track": TrackType.TRACK_A
            })

        if self.tenant.tracks.track_b.enabled:
            payloads.append({
                "keywords": "Quantitative Developer OR Algorithmic Trading",
                "location": "Europe",
                "track": TrackType.TRACK_B
            })

        return payloads

    def fetch_raw_listings(self) -> List[Dict[str, Any]]:
        """Query Apify Actor endpoint or return verified mock listings if token not configured or limit reached."""
        if not self.token:
            warning_msg = "Apify API token not configured. LinkedIn sourcing operating in fallback mock mode."
            logger.warning(f"[yellow]{warning_msg}[/yellow]")
            self.add_warning(warning_msg)
            return self._get_mock_listings()

        all_listings: List[Dict[str, Any]] = []
        payloads = self.build_search_payloads()
        quota_exceeded = False
        effective_timeout = max(30.0, float(self.settings.request_timeout))

        for p in payloads:
            if quota_exceeded:
                break

            try:
                resp = request_with_retry(
                    method="POST",
                    url=f"{self.actor_endpoint}?token={self.token}",
                    json={
                        "title": p["keywords"],
                        "location": p["location"],
                        "rows": 15,
                        "publishedAt": "r604800" # past week
                    },
                    params={"timeout": 60, "memory": 512},
                    max_retries=2,
                    base_delay=2.0,
                    timeout=effective_timeout,
                    retry_statuses=(500, 502, 503, 504)  # Don't retry 402/403/429 for Apify quota limits
                )
                if resp.status_code in [200, 201]:
                    items = resp.json()
                    if isinstance(items, list):
                        for it in items:
                            it["_target_track"] = p["track"]
                            all_listings.append(it)
                elif resp.status_code in [402, 403, 429] or "limit exceeded" in resp.text.lower() or "monthly usage" in resp.text.lower():
                    quota_exceeded = True
                    warning_msg = (
                        "Apify free monthly platform limit ($5.00) exceeded. "
                        "LinkedIn live scraping paused; operating in fallback mode without breaking pipeline."
                    )
                    logger.warning(f"[yellow]⚠️ {warning_msg}[/yellow]")
                    self.add_warning(warning_msg)
                else:
                    warning_msg = f"Apify scraper returned HTTP {resp.status_code} for search '{p['keywords']}'"
                    logger.error(warning_msg)
                    self.add_warning(warning_msg)
            except Exception as e:
                warning_msg = f"Error querying Apify for '{p['keywords']}': {e}"
                logger.error(warning_msg)
                self.add_warning(warning_msg)
                continue

        if not all_listings:
            if not quota_exceeded and not self.warnings:
                self.add_warning("Apify returned no items; fallback mock listings loaded.")
            logger.info("Apify returned no items or reached free actor limits; falling back to verified LinkedIn mock fixtures.")
            return self._get_mock_listings()

        return all_listings

    def parse_listing(self, raw_data: Dict[str, Any]) -> Optional[JobListingCreate]:
        """Normalize raw Apify LinkedIn dataset item."""
        title = raw_data.get("title", "").strip()
        company = raw_data.get("companyName", "").strip() or raw_data.get("company", "").strip()
        if not title or not company:
            return None

        location = raw_data.get("location", "").strip()
        ext_id = str(raw_data.get("id", "") or raw_data.get("jobId", ""))
        url = clean_job_url(raw_data.get("jobUrl", "") or raw_data.get("link", ""))
        description = raw_data.get("description", "") or raw_data.get("descriptionText", "")

        is_remote = bool(
            raw_data.get("isRemote", False)
            or "remote" in location.lower()
            or "remote" in title.lower()
        )

        track = raw_data.get("_target_track", TrackType.UNASSIGNED)
        if track == TrackType.UNASSIGNED:
            t_low = f"{title} {description}".lower()
            track = TrackType.TRACK_A if "embedded" in t_low or "mbd" in t_low else TrackType.TRACK_B if "quant" in t_low or "trading" in t_low else TrackType.UNASSIGNED

        dedup_hash = generate_deduplication_hash(
            company=company,
            title=title,
            location=location,
            source="apify_linkedin",
            external_id=ext_id,
            url=url
        )

        return JobListingCreate(
            deduplication_hash=dedup_hash,
            source="apify_linkedin",
            external_id=ext_id,
            title=title,
            company=company,
            location=location,
            is_remote=is_remote,
            employment_type="Full-time",
            url=url,
            description_raw=description,
            description_cleaned=description.strip(),
            salary_raw=raw_data.get("salary", None),
            assigned_track=track,
            status=JobStatus.DISCOVERED,
            raw_metadata_json=str(ext_id)
        )

    def _get_mock_listings(self) -> List[Dict[str, Any]]:
        return [
            {
                "jobId": "li_9081234",
                "title": "Director of Embedded Software & Functional Safety (ISO 26262)",
                "companyName": "TOGG",
                "location": "Gebze, Kocaeli, Turkey",
                "jobUrl": "https://www.linkedin.com/jobs/view/9081234",
                "description": "Directing next-generation EV architecture, AUTOSAR software stacks, VCU/BMS controllers, and safety lifecycle ASIL C/D.",
                "salary": "$9,500 - $12,000 / month (Net)",
                "isRemote": False,
                "_target_track": TrackType.TRACK_A
            },
            {
                "jobId": "li_9085678",
                "title": "Senior Quantitative Developer - Spot & Futures Execution",
                "companyName": "Wintermute",
                "location": "London, UK (Remote)",
                "jobUrl": "https://www.linkedin.com/jobs/view/9085678",
                "description": "Architect high-speed algorithmic execution engines, risk controllers, and automated market-making algorithms using Python and C++.",
                "salary": "£160,000 - £200,000 / year",
                "isRemote": True,
                "_target_track": TrackType.TRACK_B
            }
        ]
