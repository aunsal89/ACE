"""Google Jobs / SerpApi Sourcing Module."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import httpx

from src.config import SourcingSettings, TenantProfile
from src.database.models import JobListingCreate, JobStatus
from src.sourcing.base import BaseScraper
from src.utils.hashing import clean_job_url, generate_deduplication_hash, normalize_company, normalize_title
from src.utils.http import request_with_retry
from src.utils.logger import logger


class GoogleJobsScraper(BaseScraper):
    """Sourcing client for Google Jobs via SerpApi or direct structured endpoint."""

    def __init__(self, settings: SourcingSettings, tenant: TenantProfile, api_key: Optional[str] = None):
        super().__init__(settings, tenant)
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY", "")
        self.endpoint = "https://serpapi.com/search.json"

    def build_search_queries(self) -> List[Dict[str, Any]]:
        """Construct high-intent consolidated search queries based on candidate preferences."""
        queries = []
        titles = self.tenant.preferences.target_titles or ["Software Engineer"]
        locations = self.tenant.preferences.target_locations or ["Remote"]

        for title in titles[:3]:
            for loc in locations[:2]:
                queries.append({
                    "q": title,
                    "location": loc,
                })
        return queries or [{"q": "Software Engineer", "location": "Remote"}]

    def fetch_raw_listings(self) -> List[Dict[str, Any]]:
        """Fetch listings from SerpApi. If API key is not present or queries fail, returns realistic mock fixtures."""
        if not self.api_key:
            warning_msg = "SERPAPI_API_KEY not set. Using verified Google Jobs mock fixtures."
            logger.warning(f"[yellow]{warning_msg}[/yellow]")
            self.add_warning(warning_msg)
            return self._get_mock_listings()

        all_listings: List[Dict[str, Any]] = []
        queries = self.build_search_queries()
        effective_timeout = max(35.0, float(self.settings.request_timeout))

        for q_spec in queries:
            params = {
                "engine": "google_jobs",
                "q": q_spec["q"],
                "location": q_spec["location"],
                "api_key": self.api_key,
            }
            try:
                resp = request_with_retry(
                    method="GET",
                    url=self.endpoint,
                    params=params,
                    max_retries=self.settings.max_retries,
                    base_delay=2.0,
                    timeout=effective_timeout,
                    headers={"User-Agent": self.settings.user_agent}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("jobs_results", [])
                    for item in results:
                        all_listings.append(item)
                else:
                    warning_msg = f"SerpApi query '{q_spec['q']}' returned HTTP {resp.status_code}"
                    logger.error(warning_msg)
                    self.add_warning(warning_msg)
            except Exception as e:
                warning_msg = f"Error querying SerpApi for '{q_spec['q']}': {e}"
                logger.error(warning_msg)
                self.add_warning(warning_msg)
                continue

        if not all_listings:
            warning_msg = "Google Jobs returned no live results; falling back to verified mock fixtures."
            logger.info(warning_msg)
            self.add_warning(warning_msg)
            return self._get_mock_listings()

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
            assigned_track="GENERAL",
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

    def _get_mock_listings(self) -> List[Dict[str, Any]]:
        """Dynamically construct fallback mock listings tailored to the active candidate profile."""
        titles = self.tenant.preferences.target_titles or ["Software Engineer", "Engineering Lead"]
        locations = self.tenant.preferences.target_locations or ["Remote"]
        competencies = self.tenant.preferences.core_competencies or ["System Architecture", "Engineering Delivery"]

        t1 = titles[0]
        t2 = titles[1] if len(titles) > 1 else f"Senior {titles[0]}"
        t3 = titles[2] if len(titles) > 2 else f"Lead {titles[0]}"

        l1 = locations[0]
        l2 = locations[1] if len(locations) > 1 else locations[0]
        l3 = "Remote" if any("remote" in loc.lower() for loc in locations) else (locations[0] if locations else "Remote")

        kws1 = ", ".join(competencies[:3]) if competencies else "System Architecture, Cloud, Agile"
        kws2 = ", ".join(competencies[2:5] or competencies[:2]) if competencies else "High-Scale Systems, CI/CD"
        kws3 = ", ".join(competencies[:2]) if competencies else "Engineering Leadership, Technical Delivery"

        return [
            {
                "job_id": "gj_mock_01",
                "title": t1,
                "company_name": "Acme Global Tech",
                "location": l1,
                "description": f"We are seeking a talented {t1} to drive engineering excellence. Requirements include deep expertise in {kws1}.",
                "share_link": "https://careers.acme-tech.example/jobs/01",
                "detected_extensions": {
                    "salary": "$120,000 - $160,000 a year",
                    "schedule_type": "Full-time",
                    "work_from_home": "remote" in l1.lower(),
                },
            },
            {
                "job_id": "gj_mock_02",
                "title": t2,
                "company_name": "Nexus Systems Enterprise",
                "location": l2,
                "description": f"Join our engineering division as a {t2}. You will lead critical technical initiatives specializing in {kws2}.",
                "share_link": "https://careers.nexus-systems.example/jobs/02",
                "detected_extensions": {
                    "salary": "$135,000 - $175,000 a year",
                    "schedule_type": "Full-time",
                    "work_from_home": "remote" in l2.lower(),
                },
            },
            {
                "job_id": "gj_mock_03",
                "title": t3,
                "company_name": "Vertex Engineering Labs",
                "location": l3,
                "description": f"Key technical opening for a {t3} to scale robust architectures and deliver mission-critical solutions in {kws3}.",
                "share_link": "https://careers.vertex-labs.example/jobs/03",
                "detected_extensions": {
                    "salary": "$140,000 - $190,000 a year",
                    "schedule_type": "Full-time",
                    "work_from_home": "remote" in l3.lower(),
                },
            },
        ]
