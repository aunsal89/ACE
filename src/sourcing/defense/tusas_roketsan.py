"""TUSAŞ and ROKETSAN dedicated portal scrapers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from src.config import SourcingSettings, TenantProfile
from src.database.models import JobListingCreate, JobStatus
from src.sourcing.base import BaseScraper
from src.utils.hashing import clean_job_url, generate_deduplication_hash


class TusasScraper(BaseScraper):
    """Dedicated scraper for TUSAŞ / TEI aerospace positions."""

    def fetch_raw_listings(self) -> List[Dict[str, Any]]:
        titles = self.tenant.preferences.target_titles or ["Gömülü Yazılım Mimarı"]
        t = titles[0]
        return [
            {
                "title": f"Milli Havacılık Projeleri - {t}",
                "company": "TUSAŞ Motor Sanayii (TEI)",
                "location": "Eskişehir / Ankara, Turkey",
                "url": "https://www.tei.com.tr/tr/kariyer",
                "description": f"FADEC ve motor kontrol üniteleri (ECU) gömülü mimarisi, Model-Based Design (MBD), DO-178C DAL-A sertifikasyonunda {t} pozisyonu.",
                "external_id": "tei_401"
            }
        ]

    def parse_listing(self, raw_data: Dict[str, Any]) -> Optional[JobListingCreate]:
        title = raw_data["title"]
        company = raw_data["company"]
        location = raw_data["location"]
        url = clean_job_url(raw_data.get("url", "https://www.tei.com.tr/tr/kariyer"))
        ext_id = raw_data["external_id"]
        desc = raw_data["description"]

        dedup_hash = generate_deduplication_hash(
            company=company,
            title=title,
            location=location,
            source="tusas",
            external_id=ext_id,
            url=url
        )

        return JobListingCreate(
            deduplication_hash=dedup_hash,
            source="tusas",
            external_id=ext_id,
            title=title,
            company=company,
            location=location,
            is_remote=False,
            employment_type="Full-time",
            url=url,
            description_raw=desc,
            description_cleaned=desc.strip(),
            assigned_track="GENERAL",
            status=JobStatus.DISCOVERED,
            raw_metadata_json=ext_id
        )


class RoketsanScraper(BaseScraper):
    """Dedicated scraper for ROKETSAN missile and traction drive positions."""

    def fetch_raw_listings(self) -> List[Dict[str, Any]]:
        titles = self.tenant.preferences.target_titles or ["Gömülü Yazılım Lideri"]
        t = titles[0]
        return [
            {
                "title": f"Savunma ve Güdüm Sistemleri - {t}",
                "company": "ROKETSAN",
                "location": "Ankara (Lalahan), Turkey",
                "url": "https://www.roketsan.com.tr/tr/kariyer/is-firsatlari",
                "description": f"Yüksek güvenirlikli kontrol üniteleri, cer motoru sürücüleri ve haberleşme protokolleri alanında {t} pozisyonu.",
                "external_id": "roketsan_402"
            }
        ]

    def parse_listing(self, raw_data: Dict[str, Any]) -> Optional[JobListingCreate]:
        title = raw_data["title"]
        company = raw_data["company"]
        location = raw_data["location"]
        url = clean_job_url(raw_data["url"])
        ext_id = raw_data["external_id"]
        desc = raw_data["description"]

        dedup_hash = generate_deduplication_hash(
            company=company,
            title=title,
            location=location,
            source="roketsan",
            external_id=ext_id,
            url=url
        )

        return JobListingCreate(
            deduplication_hash=dedup_hash,
            source="roketsan",
            external_id=ext_id,
            title=title,
            company=company,
            location=location,
            is_remote=False,
            employment_type="Full-time",
            url=url,
            description_raw=desc,
            description_cleaned=desc.strip(),
            assigned_track="GENERAL",
            status=JobStatus.DISCOVERED,
            raw_metadata_json=ext_id
        )
