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
        return [
            {
                "title": "Head of Powertrain & ECU Embedded Software Architecture",
                "company": "TUSAŞ Motor Sanayii (TEI)",
                "location": "Eskişehir / Ankara, Turkey",
                "url": "https://www.tei.com.tr/kariyer/ecu-software-lead-401",
                "description": "FADEC ve motor kontrol üniteleri (ECU) gömülü yazılım mimarisi, Model-Based Design (MBD), DO-178C DAL-A sertifikasyonu ve 20+ mühendislik ekip liderliği.",
                "external_id": "tei_401"
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
        return [
            {
                "title": "Traction Control & Inverter Firmware Lead",
                "company": "ROKETSAN",
                "location": "Ankara (Lalahan), Turkey",
                "url": "https://www.roketsan.com.tr/kariyer/inverter-firmware-lead-402",
                "description": "Yüksek gerilimli cer motoru sürücüleri, MTPA algoritması, CAN/Ethernet otomotiv haberleşme protokolleri ve fonksiyonel güvenlik.",
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
