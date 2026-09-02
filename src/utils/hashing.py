"""Job deduplication and text normalization utilities."""

import hashlib
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TITLE_NOISE_REGEX = re.compile(
    r"[\(\[\{][^\)\]\}]*?(m\/w\/d|f\/m\/d|w\/m\/d|d\/m\/w|all genders|remote|hybrid|onsite|urgent|full[- ]time|contract|permanent)[^\)\]\}]*?[\)\]\}]",
    re.IGNORECASE
)

WHITESPACE_REGEX = re.compile(r"\s+")
PUNCTUATION_CLEAN_REGEX = re.compile(r"[^\w\s]")


def normalize_company(company: str) -> str:
    """Normalize company name by stripping legal forms, punctuation, and extra whitespace."""
    if not company:
        return ""
    text = company.strip().lower()
    # Strip common legal and organizational suffixes
    text = re.sub(r"\ba\.?\s*ş\.?\b|\ba\.?\s*s\.?\b", " ", text)
    text = re.sub(r"\bltd\.?\s*ş?t?i?\.?\b", " ", text)
    text = re.sub(r"\bsan\.?(?:\s+ve)?\s+tic\.?(?:\s+a\.?ş\.?)?\b", " ", text)
    text = re.sub(r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|gmbh|ag|se|co|pte|plc|holding)\b", " ", text)
    text = PUNCTUATION_CLEAN_REGEX.sub(" ", text)
    text = WHITESPACE_REGEX.sub(" ", text).strip()
    return text


def normalize_title(title: str) -> str:
    """Normalize job title by stripping noise brackets, punctuation, and extra whitespace."""
    if not title:
        return ""
    text = TITLE_NOISE_REGEX.sub("", title.strip())
    text = PUNCTUATION_CLEAN_REGEX.sub(" ", text.lower())
    text = WHITESPACE_REGEX.sub(" ", text).strip()
    return text


def normalize_location(location: Optional[str]) -> str:
    """Normalize location string."""
    if not location:
        return ""
    text = location.strip().lower()
    text = PUNCTUATION_CLEAN_REGEX.sub(" ", text)
    text = WHITESPACE_REGEX.sub(" ", text).strip()
    return text


def clean_job_url(url: Optional[str]) -> str:
    """Clean tracking parameters while strictly preserving fragments, routing, and valid URLs."""
    if not url or url.strip() in ("", "#"):
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = f"https://{u}"
    try:
        parsed = urlparse(u)
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "fbclid", "gclid", "mc_cid", "mc_eid",
            "ref", "tracking_id"
        }
        filtered_queries = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in tracking_params
        ]
        new_query = urlencode(filtered_queries)
        path = parsed.path or "/"
        cleaned_url = urlunparse((
            parsed.scheme or "https",
            parsed.netloc,
            path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        return cleaned_url
    except Exception:
        return u


def generate_deduplication_hash(
    company: str,
    title: str,
    location: Optional[str] = "",
    source: Optional[str] = "",
    external_id: Optional[str] = "",
    url: Optional[str] = ""
) -> str:
    """
    Generate deterministic SHA-256 deduplication hash for a job posting.
    Incorporates normalized company, title, location, and primary identifier.
    """
    norm_comp = normalize_company(company)
    norm_titl = normalize_title(title)
    norm_loc = normalize_location(location)

    ident = (external_id or "").strip()
    if not ident and url:
        ident = clean_job_url(url)

    composite_key = f"{norm_comp}::{norm_titl}::{norm_loc}::{ident}"
    return hashlib.sha256(composite_key.encode("utf-8")).hexdigest()


def generate_semantic_cluster_key(company: str, title: str) -> str:
    """Generate a high-level key for grouping near-duplicate postings across platforms."""
    norm_comp = normalize_company(company)
    norm_titl = normalize_title(title)
    return f"{norm_comp}::{norm_titl}"
