"""Google Jobs / SerpApi Sourcing Module."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import httpx

from src.config import SourcingSettings, TenantProfile
from src.database.models import JobListingCreate, JobStatus, TrackType
from src.sourcing.base import BaseScraper
from src.utils.hashing import clean_job_url, generate_deduplication_hash, normalize_company, normalize_title
from src.utils.logger import logger


class GoogleJobsScraper(BaseScraper):
    """Sourcing client for Google Jobs via SerpApi or direct structured endpoint."""

    def __init__(self, settings: SourcingSettings, tenant: TenantProfile, api_key: Optional[str] = None):
        super().__init__(settings, tenant)
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY", "")
        self.endpoint = "https://serpapi.com/search.json"

    def build_search_queries(self) -> List[Dict[str, Any]]:
        """Construct high-intent search queries based on Track A and Track B tenant criteria."""
        queries = []

        # Track A: Embedded Leadership (Turkey / EMEA)
        if self.tenant.tracks.track_a.enabled:
            for title in self.tenant.tracks.track_a.target_titles[:3]:
                for loc in self.tenant.tracks.track_a.target_locations:
                    queries.append({
                        "q": f"{title} in {loc}",
                        "location": loc,
                        "track": TrackType.TRACK_A,
                    })

        # Track B: Quant Developer (Europe / APAC)
        if self.tenant.tracks.track_b.enabled:
            for title in self.tenant.tracks.track_b.target_titles[:3]:
                for city in self.tenant.tracks.track_b.target_cities[:5]:
                    queries.append({
                        "q": f"{title} in {city}",
                        "location": city,
                        "track": TrackType.TRACK_B,
                    })

        return queries

    def fetch_raw_listings(self) -> List[Dict[str, Any]]:
        """Fetch listings from SerpApi. If API key is not present, returns realistic mock fixtures."""
        if not self.api_key:
            logger.warning("[yellow]SERPAPI_API_KEY not set. Using verified Google Jobs mock fixtures.[/yellow]")
            return self._get_mock_listings()

        all_listings: List[Dict[str, Any]] = []
        queries = self.build_search_queries()

        with httpx.Client(timeout=self.settings.request_timeout, headers={"User-Agent": self.settings.user_agent}) as client:
            for q_spec in queries:
                params = {
                    "engine": "google_jobs",
                    "q": q_spec["q"],
                    "location": q_spec["location"],
                    "api_key": self.api_key,
                }
                try:
                    resp = client.get(self.endpoint, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("jobs_results", [])
                        for item in results:
                            item["_target_track"] = q_spec["track"]
                            all_listings.append(item)
                    else:
                        logger.error(f"SerpApi query '{q_spec['q']}' returned status {resp.status_code}")
                except Exception as e:
                    logger.error(f"Error querying SerpApi for '{q_spec['q']}': {e}")
                    continue

        return all_listings

    def parse_listing(self, raw_data: Dict[str, Any]) -> Optional[JobListingCreate]:
        """Convert raw Google Jobs item to standardized JobListingCreate."""
        title = raw_data.get("title", "").strip()
        company = raw_data.get("company_name", "").strip()
        if not title or not company:
            return None

        location = raw_data.get("location", "").strip()
        ext_id = raw_data.get("job_id", "")
        description = raw_data.get("description", "")
        
        # Primary apply link or share link
        apply_options = raw_data.get("apply_options", [])
        url = apply_options[0].get("link", "") if apply_options else raw_data.get("share_link", "")
        url = clean_job_url(url)

        # Detect salary extensions
        detected_extensions = raw_data.get("detected_extensions", {})
        salary_raw = detected_extensions.get("salary")
        salary_min, salary_max, salary_currency = self._parse_salary(salary_raw)

        # Remote status
        is_remote = bool(
            raw_data.get("is_remote") 
            or "remote" in location.lower() 
            or "remote" in title.lower()
            or detected_extensions.get("work_from_home", False)
        )

        # Track assignment
        track = raw_data.get("_target_track", TrackType.UNASSIGNED)
        if track == TrackType.UNASSIGNED:
            track = self._classify_track(title, description)

        dedup_hash = generate_deduplication_hash(
            company=company,
            title=title,
            location=location,
            source="google_jobs",
            external_id=ext_id,
            url=url
        )

        return JobListingCreate(
            deduplication_hash=dedup_hash,
            source="google_jobs",
            external_id=ext_id,
            title=title,
            company=company,
            location=location,
            is_remote=is_remote,
            employment_type=detected_extensions.get("schedule_type", "Full-time"),
            url=url,
            description_raw=description,
            description_cleaned=description.strip(),
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            assigned_track=track,
            status=JobStatus.DISCOVERED,
            raw_metadata_json=str(raw_data.get("job_id", ""))
        )

    def _parse_salary(self, salary_str: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str]]:
        if not salary_str:
            return None, None, None
        currency = "USD" if "$" in salary_str else "EUR" if "€" in salary_str else "GBP" if "£" in salary_str else "TRY" if "₺" in salary_str or "TL" in salary_str else None
        nums = [float(n.replace(",", "")) for n in re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", salary_str)]
        if not nums:
            return None, None, currency
        if len(nums) == 1:
            return nums[0], nums[0], currency
        return min(nums), max(nums), currency

    def _classify_track(self, title: str, desc: str) -> TrackType:
        t_low = f"{title} {desc}".lower()
        has_a = any(k in t_low for k in ["embedded", "mbd", "simulink", "autosar", "pmsm", "motor control", "powertrain", "ecu", "iso 26262"])
        has_b = any(k in t_low for k in ["quant", "algorithmic trading", "execution", "hft", "ccxt", "backtest", "orderbook"])
        if has_a and has_b:
            return TrackType.BOTH
        if has_a:
            return TrackType.TRACK_A
        if has_b:
            return TrackType.TRACK_B
        return TrackType.UNASSIGNED

    def _get_mock_listings(self) -> List[Dict[str, Any]]:
        return [
            {
                "job_id": "gj_quant_ldn_01",
                "title": "Quantitative Software Engineer - Algorithmic Execution",
                "company_name": "Man Group",
                "location": "London, United Kingdom",
                "description": "Develop high-throughput algorithmic execution platforms and walk-forward backtesting pipelines in Python and C++.",
                "share_link": "https://www.man.com/careers/quant-engineer-01",
                "detected_extensions": {
                    "salary": "£140,000 - £180,000 a year",
                    "schedule_type": "Full-time",
                    "work_from_home": True
                },
                "_target_track": TrackType.TRACK_B
            },
            {
                "job_id": "gj_emb_ist_02",
                "title": "Head of Embedded Software Engineering",
                "company_name": "AVL Turkey",
                "location": "Istanbul, Turkey",
                "description": "Lead 25+ software engineers developing EV Powertrain ECUs, Inverter controls, and MBD Simulink models under ISO 26262 ASIL D and AUTOSAR.",
                "share_link": "https://www.avl.com/careers/head-of-embedded-istanbul",
                "detected_extensions": {
                    "salary": "$110,000 - $135,000 a year",
                    "schedule_type": "Full-time",
                    "work_from_home": False
                },
                "_target_track": TrackType.TRACK_A
            },
            {
                "job_id": "gj_quant_sg_03",
                "title": "Quantitative Developer - Crypto & Equities Yields",
                "company_name": "QCP Capital",
                "location": "Singapore",
                "description": "Build automated spot/derivatives execution engines with multi-layer risk management, regime detection, and low-latency exchange interfaces.",
                "share_link": "https://www.qcp.capital/careers/quant-dev",
                "detected_extensions": {
                    "salary": "$150,000 - $220,000 a year",
                    "schedule_type": "Full-time",
                    "work_from_home": True
                },
                "_target_track": TrackType.TRACK_B
            }
        ]
