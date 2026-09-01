"""
HTML Review Dashboard Generator for Career Engine staged jobs in /inbox/.
Produces a self-contained, responsive, zero-external-dependency HTML dashboard at inbox/index.html
with executive-grade light theme, dynamic taxonomy aggregation, dual-dimension filtering (Track & Status),
interactive charts, multi-term search, sorting, and force-stage action triggers for evaluated/queued listings.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import EngineConfig, TenantProfile, load_engine_config, load_tenant_profile
from src.database.models import JobListing, JobStatus, TrackType
from src.database.repository import JobRepository
from src.utils.logger import logger


def normalize_region_group(location: Optional[str], is_remote: bool = False) -> str:
    """Dynamically normalize free-text location into high-signal geographical region groupings."""
    if not location or location.strip() == "":
        return "Remote / Anywhere" if is_remote else "Unspecified"
    loc = location.strip()
    loc_l = loc.lower()

    if "singapore" in loc_l:
        return "Singapore"
    if any(k in loc_l for k in ("turkey", "türkiye", "ankara", "istanbul", "gebze", "kocaeli", "eskişehir", "hadımköy", "elmadağ")):
        if any(k in loc_l for k in ("istanbul", "gebze", "kocaeli", "marmara", "hadımköy")):
            return "Turkey (Istanbul / Marmara)"
        if any(k in loc_l for k in ("ankara", "eskişehir", "elmadağ", "kahramankazan", "macunköy", "lalahan")):
            return "Turkey (Ankara)"
        return "Turkey (Other)"
    if any(k in loc_l for k in ("united kingdom", "england", "london", "uk", "cambridge", "bristol", "norwich", "norfolk", "gloucester", "hampshire", "doncaster", "hull")):
        if "london" in loc_l:
            return "UK (London)"
        return "UK (Regional / Other)"
    if any(k in loc_l for k in ("germany", "deutschland", "munich", "kassel", "ulm", "dissen", "manching", "bavaria", "hesse")):
        return "Germany"
    if any(k in loc_l for k in ("netherlands", "eindhoven", "nootdorp", "brabant", "holland")):
        return "Netherlands"
    if any(k in loc_l for k in ("china", "suzhou", "wuxi", "changzhou", "shanghai", "beijing", "shenzhen")):
        return "China (APAC Hubs)"
    if any(k in loc_l for k in ("hong kong", "hk")):
        return "Hong Kong"
    if any(k in loc_l for k in ("switzerland", "zurich", "geneva")):
        return "Switzerland"
    if any(k in loc_l for k in ("remote", "anywhere")):
        return "Remote / Anywhere"

    # Dynamic fallback: Extract city and country
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    if len(parts) >= 2:
        return f"{parts[-2]}, {parts[-1]}"
    elif parts:
        return parts[-1]
    return "Other Regions"


def normalize_position_group(title: Optional[str]) -> str:
    """Dynamically normalize free-text job title into executive role taxonomy."""
    if not title:
        return "Specialized Technical"
    t = title.lower()

    # Executive & Engineering Leadership
    if any(k in t for k in ("head of", "director", "abteilungsleiter", "fachbereichsleiter", "engineering manager", "software project manager", "müdür", "vp", "chief")):
        return "Executive & Engineering Leadership"
    # System Architecture & Technical Leads
    if any(k in t for k in ("principal", "architect", "mimar", "tech lead", "technical lead", "lead engineer", "takım lideri")):
        return "Lead / Principal / Architecture"
    # Embedded & Firmware Systems
    if any(k in t for k in ("embedded", "gömülü", "firmware", "rtos", "autosar", "bms", "vcu", "mcu", "dsp")):
        return "Embedded & Firmware Systems"
    # Control Systems & Robotics
    if any(k in t for k in ("flight control", "uçuş kontrol", "aviyonik", "avionics", "güdüm", "guidance", "robotics", "motor control", "traction control", "inverter", "power electronics", "güç elektroniği")):
        return "Control Systems & Robotics"
    # AI, ML & Data Science
    if any(k in t for k in ("machine learning", "deep learning", "data scientist", "data engineer", "ai engineer", "computer vision", "nlp", "llm")):
        return "AI, ML & Data Science"
    # Distributed Systems & Cloud Infrastructure
    if any(k in t for k in ("cloud", "devops", "site reliability", "sre", "infrastructure", "kubernetes", "distributed systems", "backend")):
        return "Cloud & Distributed Systems"
    # Quantitative & Trading Systems
    if any(k in t for k in ("quantitative", "quant", "algorithmic trading", "trading systems", "execution engine")):
        return "Quantitative & Algorithmic Systems"

    # Dynamic token extraction for arbitrary titles
    clean_t = re.sub(r"[\(\)\[\]/\-,\|]", " ", t)
    words = clean_t.split()
    stop_words = {"and", "or", "the", "in", "of", "for", "with", "at", "senior", "junior", "staff", "iii", "ii", "i", "level", "m/w/d", "w/m/d", "f/m/d", "all", "genders"}
    cleaned_words = [w.capitalize() for w in words if w not in stop_words and len(w) > 2]
    if len(cleaned_words) >= 2:
        return f"{cleaned_words[0]} {cleaned_words[1]}"
    elif cleaned_words:
        return f"{cleaned_words[0]} Engineering"
    return "Specialized Engineering"


def generate_inbox_dashboard(
    config: Optional[EngineConfig] = None,
    tenant: Optional[TenantProfile] = None,
    output_html_path: Optional[Path | str] = None,
) -> Path:
    """
    Generate or regenerate the HTML review dashboard in the inbox directory.
    All links to folders and documents are strictly relative to the HTML file location.
    """
    config = config or load_engine_config()
    tenant = tenant or load_tenant_profile(config=config)
    repo = JobRepository(config.database.db_path)

    inbox_dir = config.engine.inbox_dir
    target_html = Path(output_html_path) if output_html_path else inbox_dir / "index.html"
    target_html.parent.mkdir(parents=True, exist_ok=True)

    # Query all jobs and evaluations
    all_jobs = repo.list_jobs(limit=1000)
    packages = repo.get_application_packages()
    pkgs_by_job_id = {p.job_id: p for p in packages}

    # Also scan disk for any staged folders under inbox_dir
    disk_folders_by_job_id: Dict[str, Path] = {}
    for item in inbox_dir.rglob("*"):
        if item.is_dir():
            parts = item.name.split("_")
            if parts:
                short_id = parts[-1]
                if len(short_id) == 8:
                    disk_folders_by_job_id[short_id] = item

    job_cards_data: List[Dict[str, Any]] = []

    for job in all_jobs:
        evals = repo.get_evaluations_for_job(job.id)
        latest_eval = evals[0] if evals else None
        pkg = pkgs_by_job_id.get(job.id)

        # Locate staged folder on disk if present
        folder_rel_path: Optional[str] = None
        resume_pdf_rel: Optional[str] = None
        cover_pdf_rel: Optional[str] = None
        resume_md_rel: Optional[str] = None
        cover_md_rel: Optional[str] = None
        linkedin_md_rel: Optional[str] = None
        details_md_rel: Optional[str] = None

        staged_dir: Optional[Path] = None
        if pkg and pkg.resume_pdf_path:
            pkg_path = Path(pkg.resume_pdf_path).parent
            if pkg_path.exists():
                staged_dir = pkg_path
        if not staged_dir:
            staged_dir = disk_folders_by_job_id.get(job.id[:8])

        if staged_dir and staged_dir.exists():
            try:
                rel = os.path.relpath(staged_dir, inbox_dir)
                folder_rel_path = f"./{rel}"
                for f in staged_dir.iterdir():
                    if f.name.endswith(".pdf") and "Resume" in f.name:
                        resume_pdf_rel = f"./{os.path.relpath(f, inbox_dir)}"
                    elif f.name.endswith(".pdf") and "Cover_Letter" in f.name:
                        cover_pdf_rel = f"./{os.path.relpath(f, inbox_dir)}"
                    elif f.name.endswith(".md") and "Resume" in f.name:
                        resume_md_rel = f"./{os.path.relpath(f, inbox_dir)}"
                    elif f.name.endswith(".md") and "Cover_Letter" in f.name:
                        cover_md_rel = f"./{os.path.relpath(f, inbox_dir)}"
                    elif f.name == "LinkedIn_Guidance.md":
                        linkedin_md_rel = f"./{os.path.relpath(f, inbox_dir)}"
                    elif f.name == "Job_Details.md":
                        details_md_rel = f"./{os.path.relpath(f, inbox_dir)}"
            except Exception:
                pass

        score_val = latest_eval.overall_score if latest_eval else None
        rec_val = latest_eval.recommendation.value if latest_eval else "UNSCORRED"
        reasoning = latest_eval.reasoning if latest_eval else ""

        matched_kws = []
        if latest_eval and latest_eval.matched_keywords_json:
            try:
                matched_kws = json.loads(latest_eval.matched_keywords_json)
            except Exception:
                pass

        region_group = normalize_region_group(job.location, job.is_remote)
        pos_group = normalize_position_group(job.title)
        job_track = job.assigned_track.value if hasattr(job.assigned_track, "value") else str(job.assigned_track or "GENERAL")

        job_cards_data.append({
            "id": job.id,
            "short_id": job.id[:8],
            "title": job.title,
            "company": job.company,
            "location": job.location or "Location Not Specified",
            "region_group": region_group,
            "position_group": pos_group,
            "is_remote": job.is_remote,
            "track": job_track,
            "status": job.status.value,
            "source": job.source,
            "url": job.url or "#",
            "discovered_at": job.discovered_at.strftime("%Y-%m-%d %H:%M") if job.discovered_at else "",
            "discovered_ts": job.discovered_at.timestamp() if job.discovered_at else 0,
            "description": job.description_cleaned or job.description_raw or "",
            "score": score_val,
            "recommendation": rec_val,
            "reasoning": reasoning,
            "matched_keywords": matched_kws,
            "folder_rel_path": folder_rel_path,
            "resume_pdf_rel": resume_pdf_rel,
            "cover_pdf_rel": cover_pdf_rel,
            "resume_md_rel": resume_md_rel,
            "cover_md_rel": cover_md_rel,
            "linkedin_md_rel": linkedin_md_rel,
            "details_md_rel": details_md_rel,
        })

    # Dynamic metrics calculation
    total_count = len(job_cards_data)
    pending_count = sum(1 for j in job_cards_data if j.get("folder_rel_path"))
    approved_count = sum(1 for j in job_cards_data if j["status"] == "APPLIED")
    rejected_count = sum(1 for j in job_cards_data if j["status"] == "REJECTED")
    queued_count = sum(1 for j in job_cards_data if j["status"] == "QUEUED" and not j.get("folder_rel_path"))
    evaluated_count = sum(1 for j in job_cards_data if j["status"] == "EVALUATED" and not j.get("folder_rel_path"))
    high_fit_count = sum(1 for j in job_cards_data if (j.get("score") or 0) >= 80)
    mid_fit_count = sum(1 for j in job_cards_data if 60 <= (j.get("score") or 0) < 80)
    low_fit_count = sum(1 for j in job_cards_data if (j.get("score") or 0) < 60)
    remote_count = sum(1 for j in job_cards_data if j.get("is_remote"))

    html_content = _build_html_template(
        tenant=tenant,
        job_cards=job_cards_data,
        stats={
            "total": total_count,
            "high_fit": high_fit_count,
            "mid_fit": mid_fit_count,
            "low_fit": low_fit_count,
            "pending": pending_count,
            "approved": approved_count,
            "rejected": rejected_count,
            "queued": queued_count,
            "evaluated": evaluated_count,
            "remote": remote_count,
        },
        generated_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    target_html.write_text(html_content, encoding="utf-8")
    logger.info(f"Dashboard generated successfully at {target_html}")
    return target_html


def _build_html_template(
    tenant: TenantProfile,
    job_cards: List[Dict[str, Any]],
    stats: Dict[str, int],
    generated_time: str,
) -> str:
    """Render self-contained, executive-grade light HTML dashboard with interactive charts."""
    jobs_json = json.dumps(job_cards, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Career Engine — Executive Sourcing & Review Dashboard</title>
  <style>
    :root {{
      --bg-page: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-subtle: #f1f5f9;
      --border-subtle: #e2e8f0;
      --border-strong: #cbd5e1;
      --text-main: #0f172a;
      --text-muted: #475569;
      --text-dim: #64748b;
      --accent-blue: #2563eb;
      --accent-blue-light: #eff6ff;
      --accent-amber: #d97706;
      --accent-amber-light: #fffbeb;
      --accent-emerald: #059669;
      --accent-emerald-light: #ecfdf5;
      --accent-purple: #7c3aed;
      --accent-purple-light: #faf5ff;
      --accent-rose: #dc2626;
      --accent-rose-light: #fef2f2;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04);
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
    }}
    body {{
      background-color: var(--bg-page);
      color: var(--text-main);
      padding: 20px 24px 60px 24px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}
    .container {{
      max-width: 1440px;
      margin: 0 auto;
    }}
    header.header-panel {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 20px 24px;
      margin-bottom: 16px;
      box-shadow: var(--shadow-sm);
    }}
    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 14px;
    }}
    .header-title h1 {{
      font-size: 21px;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
      letter-spacing: -0.01em;
    }}
    .header-title p {{
      color: var(--text-muted);
      font-size: 13px;
      margin-top: 3px;
    }}
    .time-badge {{
      font-size: 12px;
      font-weight: 500;
      background: var(--bg-surface-subtle);
      color: var(--text-muted);
      border: 1px solid var(--border-subtle);
      padding: 4px 12px;
      border-radius: 20px;
    }}
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 10px;
    }}
    .stat-card {{
      background: var(--bg-page);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px 12px;
      text-align: left;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .stat-card:hover {{
      background: var(--bg-surface-subtle);
      border-color: var(--border-strong);
      transform: translateY(-1px);
    }}
    .stat-card .val {{
      font-size: 19px;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.2;
    }}
    .stat-card .label {{
      font-size: 10.5px;
      font-weight: 600;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-top: 3px;
    }}

    /* Analytics Overview Section */
    .analytics-panel {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      margin-bottom: 16px;
      box-shadow: var(--shadow-sm);
      overflow: hidden;
      transition: all 0.2s ease;
    }}
    .analytics-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 18px;
      background: var(--bg-surface-subtle);
      border-bottom: 1px solid var(--border-subtle);
      cursor: pointer;
      user-select: none;
    }}
    .analytics-header:hover {{
      background: #e9eef5;
    }}
    .analytics-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      font-weight: 700;
      color: var(--text-main);
    }}
    .analytics-subtitle {{
      font-size: 12px;
      font-weight: 400;
      color: var(--text-dim);
    }}
    .toggle-btn {{
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
    }}
    .analytics-content {{
      padding: 16px 18px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .chart-box {{
      background: var(--bg-page);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
    }}
    .chart-box h3 {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .chart-box h3 .chart-hint {{
      font-size: 10px;
      font-weight: 500;
      color: var(--accent-blue);
      text-transform: none;
    }}
    .chart-items-list {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-height: 220px;
      overflow-y: auto;
      padding-right: 4px;
    }}
    .chart-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 8px;
      border-radius: 5px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s;
      position: relative;
      overflow: hidden;
    }}
    .chart-row:hover {{
      border-color: var(--accent-blue);
      background: var(--accent-blue-light);
    }}
    .chart-row.active {{
      border-color: var(--accent-blue);
      background: var(--accent-blue-light);
      font-weight: 700;
      box-shadow: inset 3px 0 0 var(--accent-blue);
    }}
    .chart-row-bar {{
      position: absolute;
      top: 0;
      left: 0;
      bottom: 0;
      background: rgba(37, 99, 235, 0.08);
      pointer-events: none;
      z-index: 1;
    }}
    .chart-row-content {{
      position: relative;
      z-index: 2;
      display: flex;
      justify-content: space-between;
      width: 100%;
      align-items: center;
    }}
    .chart-row-label {{
      color: var(--text-main);
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 200px;
    }}
    .chart-row-val {{
      color: var(--text-dim);
      font-weight: 600;
      font-size: 11px;
      margin-left: 8px;
    }}

    /* Donut chart SVG styling */
    .donut-container {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 14px;
      padding: 4px 0;
    }}
    .donut-svg {{
      width: 90px;
      height: 90px;
      transform: rotate(-90deg);
    }}
    .donut-legend {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
    }}
    .donut-legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      padding: 3px 6px;
      border-radius: 4px;
      transition: background 0.15s;
    }}
    .donut-legend-item:hover, .donut-legend-item.active {{
      background: var(--accent-blue-light);
      font-weight: 600;
    }}
    .legend-color-dot {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      display: inline-block;
    }}

    /* Persistent Sticky Navigation Bar */
    .sticky-controls {{
      position: sticky;
      top: 0;
      z-index: 900;
      background: rgba(255, 255, 255, 0.97);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 12px 16px;
      margin-bottom: 16px;
      box-shadow: var(--shadow-md);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .controls-row-1 {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }}
    .search-wrapper {{
      flex: 1;
      min-width: 280px;
      position: relative;
      display: flex;
      align-items: center;
    }}
    .search-wrapper input {{
      width: 100%;
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      color: var(--text-main);
      padding: 8px 34px 8px 12px;
      border-radius: 6px;
      font-size: 13px;
      outline: none;
      transition: all 0.15s;
    }}
    .search-wrapper input:focus {{
      border-color: var(--accent-blue);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }}
    .search-clear-btn {{
      position: absolute;
      right: 10px;
      background: none;
      border: none;
      color: var(--text-dim);
      font-size: 14px;
      cursor: pointer;
      display: none;
      padding: 2px 4px;
    }}
    .search-clear-btn:hover {{
      color: var(--text-main);
    }}
    .sort-control {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .sort-control label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-dim);
      white-space: nowrap;
    }}
    .sort-control select {{
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      color: var(--text-main);
      padding: 7px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      outline: none;
      cursor: pointer;
    }}
    .sort-control select:focus {{
      border-color: var(--accent-blue);
    }}

    .controls-row-2 {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      border-top: 1px solid var(--border-subtle);
      padding-top: 8px;
    }}
    .nav-filters-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .filter-pills-label {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-dim);
    }}
    .filter-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
    }}
    .pill {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .pill:hover {{
      border-color: var(--border-strong);
      color: var(--text-main);
      background: var(--bg-surface-subtle);
    }}
    .pill.active {{
      background: var(--accent-blue);
      color: #ffffff;
      border-color: var(--accent-blue);
      box-shadow: var(--shadow-sm);
    }}
    .pill-sub-toggle {{
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 4px;
    }}
    .pill-sub-toggle.active {{
      background: var(--text-main);
      color: #ffffff;
      border-color: var(--text-main);
    }}

    .active-filter-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
    }}
    .active-filter-tag {{
      background: var(--accent-blue-light);
      color: var(--accent-blue);
      border: 1px solid rgba(37, 99, 235, 0.25);
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 11px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .active-filter-tag .tag-remove {{
      cursor: pointer;
      font-size: 13px;
      line-height: 1;
      font-weight: bold;
    }}
    .btn-reset-filters {{
      background: none;
      border: 1px dashed var(--border-strong);
      color: var(--text-dim);
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 11px;
      cursor: pointer;
      font-weight: 600;
    }}
    .btn-reset-filters:hover {{
      background: var(--bg-surface-subtle);
      color: var(--text-main);
      border-color: var(--text-muted);
    }}
    .results-count-bar {{
      font-size: 12px;
      color: var(--text-dim);
      font-weight: 500;
    }}

    /* Staged Sub-selector Banner */
    .staged-subnav {{
      background: var(--accent-blue-light);
      border: 1px solid rgba(37, 99, 235, 0.2);
      border-radius: 6px;
      padding: 6px 12px;
      display: none;
      align-items: center;
      gap: 8px;
      font-size: 12px;
    }}
    .staged-subnav-label {{
      font-weight: 600;
      color: var(--accent-blue);
    }}

    /* Jobs Grid */
    .jobs-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }}
    .job-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 16px 18px;
      transition: all 0.15s ease;
      box-shadow: var(--shadow-sm);
    }}
    .job-card:hover {{
      border-color: var(--border-strong);
      box-shadow: var(--shadow-md);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .card-title-group h2 {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.01em;
    }}
    .card-title-group .company {{
      font-size: 13px;
      font-weight: 600;
      color: var(--accent-blue);
      margin-top: 2px;
    }}
    .card-meta {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 5px;
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .badges {{
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .badge {{
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      letter-spacing: 0.02em;
    }}
    .badge-remote {{
      background: #ecfdf5;
      color: #065f46;
      border: 1px solid #a7f3d0;
    }}
    .badge-source {{
      background: var(--bg-surface-subtle);
      color: var(--text-muted);
      border: 1px solid var(--border-subtle);
    }}
    .badge-queued {{
      background: var(--accent-blue-light);
      color: var(--accent-blue);
      border: 1px solid rgba(37, 99, 235, 0.3);
    }}
    .badge-evaluated {{
      background: #fef3c7;
      color: #92400e;
      border: 1px solid #fde68a;
    }}
    .badge-applied {{
      background: var(--accent-emerald-light);
      color: var(--accent-emerald);
      border: 1px solid rgba(5, 150, 105, 0.3);
    }}
    .badge-rejected {{
      background: var(--accent-rose-light);
      color: var(--accent-rose);
      border: 1px solid rgba(220, 38, 38, 0.3);
    }}
    .badge-discovered {{
      background: var(--bg-surface-subtle);
      color: var(--text-dim);
      border: 1px solid var(--border-subtle);
    }}
    .score-badge {{
      font-size: 11px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid transparent;
    }}
    .score-high {{
      background: var(--accent-emerald-light);
      color: var(--accent-emerald);
      border-color: rgba(5, 150, 105, 0.3);
    }}
    .score-mid {{
      background: var(--accent-amber-light);
      color: var(--accent-amber);
      border-color: rgba(217, 119, 6, 0.3);
    }}
    .score-low {{
      background: var(--accent-rose-light);
      color: var(--accent-rose);
      border-color: rgba(220, 38, 38, 0.3);
    }}

    .ai-rationale-box {{
      font-size: 12px;
      color: var(--text-muted);
      background: var(--bg-surface-subtle);
      padding: 8px 12px;
      border-radius: 6px;
      border-left: 3px solid var(--accent-blue);
      margin-top: 10px;
    }}
    .ai-rationale-box strong {{
      color: var(--text-main);
    }}

    details.desc-accordion {{
      margin-top: 10px;
      background: var(--bg-page);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 7px 11px;
    }}
    details.desc-accordion summary {{
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      outline: none;
      user-select: none;
    }}
    details.desc-accordion summary:hover {{
      color: var(--text-main);
    }}
    .desc-content {{
      margin-top: 8px;
      font-size: 12px;
      color: var(--text-muted);
      white-space: pre-wrap;
      max-height: 240px;
      overflow-y: auto;
      padding-right: 8px;
      border-top: 1px solid var(--border-subtle);
      padding-top: 8px;
      line-height: 1.6;
    }}

    .actions-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--border-subtle);
      align-items: center;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 12px;
      font-weight: 600;
      padding: 5px 11px;
      border-radius: 6px;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.15s;
      border: 1px solid var(--border-strong);
      background: var(--bg-surface);
      color: var(--text-muted);
    }}
    .btn:hover {{
      background: var(--bg-surface-subtle);
      color: var(--text-main);
      border-color: var(--text-dim);
    }}
    .btn-primary {{
      background: var(--accent-blue-light);
      border-color: rgba(37, 99, 235, 0.35);
      color: var(--accent-blue);
    }}
    .btn-primary:hover {{
      background: #dbeafe;
      border-color: var(--accent-blue);
    }}
    .btn-stage {{
      background: #fef3c7;
      border-color: #fde68a;
      color: #92400e;
      font-weight: 700;
    }}
    .btn-stage:hover {{
      background: #fde68a;
      border-color: #d97706;
    }}
    .btn-approve {{
      background: var(--accent-emerald-light);
      border-color: rgba(5, 150, 105, 0.35);
      color: var(--accent-emerald);
    }}
    .btn-approve:hover {{
      background: #d1fae5;
      border-color: var(--accent-emerald);
    }}
    .btn-reject {{
      background: var(--accent-rose-light);
      border-color: rgba(220, 38, 38, 0.35);
      color: var(--accent-rose);
    }}
    .btn-reject:hover {{
      background: #fee2e2;
      border-color: var(--accent-rose);
    }}
    .btn-folder {{
      background: var(--accent-amber-light);
      border-color: rgba(217, 119, 6, 0.35);
      color: var(--accent-amber);
    }}
    .btn-folder:hover {{
      background: #fef3c7;
      border-color: var(--accent-amber);
    }}
    .btn-url {{
      background: var(--accent-purple-light);
      border-color: rgba(124, 58, 237, 0.35);
      color: var(--accent-purple);
    }}
    .btn-url:hover {{
      background: #f3e8ff;
      border-color: var(--accent-purple);
    }}

    .job-id-tag {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      background: var(--bg-surface-subtle);
      border: 1px solid var(--border-subtle);
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--text-dim);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }}
    .job-id-tag:hover {{
      color: var(--accent-blue);
      border-color: var(--accent-blue);
      background: var(--accent-blue-light);
    }}

    .toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--text-main);
      color: #ffffff;
      font-weight: 500;
      font-size: 13px;
      padding: 10px 18px;
      border-radius: 8px;
      box-shadow: var(--shadow-lg);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease-in-out;
      z-index: 9999;
    }}
    .toast.show {{
      opacity: 1;
    }}
    .btn-hire-creator {{
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: #ffffff;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: var(--shadow-sm);
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .btn-hire-creator:hover {{
      background: linear-gradient(135deg, #1d4ed8, #1e40af);
      transform: translateY(-1px);
      box-shadow: var(--shadow-md);
    }}
    .btn-sponsor-creator {{
      background: linear-gradient(135deg, #d97706, #b45309);
      color: #ffffff;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: var(--shadow-sm);
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .btn-sponsor-creator:hover {{
      background: linear-gradient(135deg, #b45309, #92400e);
      transform: translateY(-1px);
      box-shadow: var(--shadow-md);
    }}
    .btn-gh-repo {{
      background: var(--bg-surface-subtle);
      color: var(--text-main);
      border: 1px solid var(--border-strong);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
    }}
    .btn-gh-repo:hover {{
      background: var(--border-subtle);
    }}

    /* Modal Backdrop & Dialog */
    .modal-backdrop {{
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(4px);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 10000;
    }}
    .modal-backdrop.show {{
      display: flex;
    }}
    .modal-box {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      width: 90%;
      max-width: 580px;
      padding: 24px 28px;
      box-shadow: var(--shadow-lg);
      position: relative;
      animation: modalFadeIn 0.2s ease-out;
    }}
    @keyframes modalFadeIn {{
      from {{ opacity: 0; transform: scale(0.96); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}
    .modal-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .modal-header h2 {{
      font-size: 18px;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .modal-close {{
      background: none;
      border: none;
      font-size: 20px;
      color: var(--text-dim);
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 4px;
    }}
    .modal-close:hover {{
      background: var(--bg-surface-subtle);
      color: var(--text-main);
    }}
    .modal-body {{
      font-size: 13.5px;
      color: var(--text-muted);
      line-height: 1.6;
    }}
    .modal-body p {{
      margin-bottom: 12px;
    }}
    .donation-links {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin: 16px 0;
    }}
    .donation-btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      text-decoration: none;
      transition: all 0.15s ease;
    }}
    .btn-gh-sponsor {{
      background: #ea4aaa;
      color: #ffffff;
    }}
    .btn-gh-sponsor:hover {{
      background: #d83296;
    }}
    .btn-bmc {{
      background: #ffdd00;
      color: #000000;
    }}
    .btn-bmc:hover {{
      background: #f0ce00;
    }}
    .crypto-box {{
      background: var(--bg-surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px;
      margin-top: 12px;
      font-size: 12px;
    }}
    .crypto-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      font-family: ui-monospace, SFMono-Regular, monospace;
    }}
    .btn-copy-addr {{
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      padding: 2px 6px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 11px;
    }}

    .empty-state {{
      text-align: center;
      padding: 40px 24px;
      background: var(--bg-surface);
      border: 1px dashed var(--border-strong);
      border-radius: 10px;
      color: var(--text-dim);
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="header-panel">
      <div class="header-top">
        <div class="header-title">
          <h1>⚡ Autonomous Career Engine (ACE)</h1>
          <p>Candidate: <strong>{html.escape(tenant.name)}</strong> ({html.escape(tenant.tenant_id)}) &nbsp;|&nbsp; Autonomous Sourcing & Application Orchestrator</p>
        </div>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <button class="btn-hire-creator" onclick="openHireModal()">💼 Hire the Creator</button>
          <button class="btn-sponsor-creator" onclick="openSponsorModal()">☕ Sponsor / Donate</button>
          <a href="https://github.com/aunsal89/ACE" target="_blank" class="btn-gh-repo">⭐ GitHub Repo</a>
          <div class="time-badge">Refreshed: {generated_time}</div>
        </div>
      </div>
      <div class="stats-bar">
        <div class="stat-card" onclick="setPrimaryFilter('all')">
          <div class="val" id="stat-total">{stats["total"]}</div>
          <div class="label">Total Sourced</div>
        </div>
        <div class="stat-card" onclick="setScoreTierFilter('high')">
          <div class="val" style="color: var(--accent-emerald);">{stats["high_fit"]}</div>
          <div class="label">High Fit (80%+)</div>
        </div>
        <div class="stat-card" onclick="setPrimaryFilter('queued')">
          <div class="val" style="color: var(--accent-blue);">{stats["queued"]}</div>
          <div class="label">Queued (Ready)</div>
        </div>
        <div class="stat-card" onclick="setPrimaryFilter('staged')">
          <div class="val" style="color: var(--accent-purple);">{stats["pending"]}</div>
          <div class="label">Staged Packages</div>
        </div>
        <div class="stat-card" onclick="setPrimaryFilter('evaluated')">
          <div class="val" style="color: var(--accent-amber);">{stats["evaluated"]}</div>
          <div class="label">Evaluated (Review)</div>
        </div>
        <div class="stat-card" onclick="setPrimaryFilter('applied')">
          <div class="val" style="color: var(--accent-emerald);">{stats["approved"]}</div>
          <div class="label">Applied</div>
        </div>
        <div class="stat-card" onclick="setPrimaryFilter('rejected')">
          <div class="val" style="color: var(--accent-rose);">{stats["rejected"]}</div>
          <div class="label">Rejected</div>
        </div>
      </div>
    </header>

    <!-- Visual Analytics Overview Panel -->
    <div class="analytics-panel">
      <div class="analytics-header" onclick="toggleAnalytics()">
        <div class="analytics-title">
          <span>📊 Interactive Sourcing & Pipeline Overview</span>
          <span class="analytics-subtitle">(Click any chart segment, region, or role group to filter)</span>
        </div>
        <button class="toggle-btn" id="analyticsToggleBtn">▾ Hide Overview</button>
      </div>
      <div class="analytics-content" id="analyticsContent">
        <!-- Fit Score Distribution Donut -->
        <div class="chart-box">
          <h3>🎯 Fit Score Breakdown <span class="chart-hint">Click segment to filter</span></h3>
          <div class="donut-container" id="fitDonutContainer">
            <!-- Rendered dynamically by JS -->
          </div>
        </div>

        <!-- Geographical Regions Bar Chart -->
        <div class="chart-box">
          <h3>📍 Dynamic Regions & Hubs <span class="chart-hint">Click region to filter</span></h3>
          <div class="chart-items-list" id="regionsChartList">
            <!-- Rendered dynamically by JS -->
          </div>
        </div>

        <!-- Position & Role Groupings -->
        <div class="chart-box">
          <h3>💼 Dynamic Role Taxonomy <span class="chart-hint">Click role to filter</span></h3>
          <div class="chart-items-list" id="positionsChartList">
            <!-- Rendered dynamically by JS -->
          </div>
        </div>

        <!-- Application Pipeline Status -->
        <div class="chart-box">
          <h3>📋 Application Pipeline <span class="chart-hint">Click status to filter</span></h3>
          <div class="chart-items-list" id="statusChartList">
            <!-- Rendered dynamically by JS -->
          </div>
        </div>
      </div>
    </div>

    <!-- Persistent Sticky Controls Bar -->
    <div class="sticky-controls">
      <div class="controls-row-1">
        <div class="search-wrapper">
          <input type="text" id="searchInput" placeholder='Search by title, company, location, keywords (e.g. "Istanbul + Lead", "Remote", ID...)' autocomplete="off" />
          <button class="search-clear-btn" id="searchClearBtn" onclick="clearSearch()" title="Clear Search">✕</button>
        </div>
        <div class="sort-control">
          <label for="sortSelect">Sort By:</label>
          <select id="sortSelect" onchange="handleSortChange(this.value)">
            <option value="date_desc">📅 Discovered: Newest First</option>
            <option value="date_asc">📅 Discovered: Oldest First</option>
            <option value="score_desc">⭐ Score: Highest First</option>
            <option value="title_asc">🔤 Title: A → Z</option>
            <option value="title_desc">🔤 Title: Z → A</option>
            <option value="company_asc">🏢 Company: A → Z</option>
          </select>
        </div>
      </div>

      <div class="controls-row-2">
        <div class="nav-filters-group">
          <!-- Primary Status Tabs -->
          <div class="filter-pills" id="statusFilterPills">
            <span class="filter-pills-label">Status:</span>
            <button class="pill active" data-filter="all" onclick="setPrimaryFilter('all')">All ({stats["total"]})</button>
            <button class="pill" data-filter="staged" onclick="setPrimaryFilter('staged')">📦 Staged Packages ({stats["pending"]})</button>
            <button class="pill" data-filter="queued" onclick="setPrimaryFilter('queued')">⏳ Queued ({stats["queued"]})</button>
            <button class="pill" data-filter="evaluated" onclick="setPrimaryFilter('evaluated')">🔬 Evaluated ({stats["evaluated"]})</button>
            <button class="pill" data-filter="applied" onclick="setPrimaryFilter('applied')">🚀 Applied ({stats["approved"]})</button>
            <button class="pill" data-filter="rejected" onclick="setPrimaryFilter('rejected')">❌ Rejected ({stats["rejected"]})</button>
          </div>

          <!-- Fit Score Tier Filter Tabs -->
          <div class="filter-pills" id="scoreFilterPills">
            <span class="filter-pills-label">Match:</span>
            <button class="pill pill-sub-toggle active" data-score="all" onclick="setScoreTierFilter('all')">All Matches</button>
            <button class="pill pill-sub-toggle" data-score="high" onclick="setScoreTierFilter('high')">High Fit (80%+)</button>
            <button class="pill pill-sub-toggle" data-score="mid" onclick="setScoreTierFilter('mid')">Review (60-79%)</button>
            <button class="pill pill-sub-toggle" data-score="low" onclick="setScoreTierFilter('low')">Low Fit (&lt;60%)</button>
          </div>

          <!-- Workplace Filter Tabs -->
          <div class="filter-pills" id="workplaceFilterPills">
            <span class="filter-pills-label">Mode:</span>
            <button class="pill pill-sub-toggle active" data-workplace="all" onclick="setWorkplaceFilter('all')">All Modes</button>
            <button class="pill pill-sub-toggle" data-workplace="remote" onclick="setWorkplaceFilter('remote')">Remote Only ({stats["remote"]})</button>
            <button class="pill pill-sub-toggle" data-workplace="onsite" onclick="setWorkplaceFilter('onsite')">On-site / Hybrid</button>
          </div>
        </div>

        <div class="active-filter-tags" id="activeFilterTags"></div>
        <div class="results-count-bar" id="resultsCountBar"></div>
      </div>

      <!-- Dedicated Staged Packages Sub-Filter Banner -->
      <div class="staged-subnav" id="stagedSubNav">
        <span class="staged-subnav-label">📦 Staged Packages Filter:</span>
        <span style="color: var(--accent-blue); font-weight: 500;">Showing {stats["pending"]} customized resume & cover letter dossiers generated in /inbox/</span>
      </div>
    </div>

    <!-- Jobs Grid Container -->
    <div class="jobs-grid" id="jobsGrid"></div>
  </div>

  <div id="toast" class="toast">Command copied to clipboard!</div>

  <script>
    const JOBS = {jobs_json};
    let currentFilter = "all";         // 'all', 'staged', 'queued', 'evaluated', 'applied', 'rejected'
    let currentScoreTier = "all";      // 'all', 'high', 'mid', 'low'
    let currentWorkplace = "all";      // 'all', 'remote', 'onsite'
    let selectedRegion = null;
    let selectedPosition = null;
    let searchQuery = "";
    let currentSort = "date_desc";
    let isAnalyticsVisible = true;

    function showToast(msg) {{
      const toast = document.getElementById("toast");
      toast.innerText = msg || "Copied to clipboard!";
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 2200);
    }}

    function copyToClipboard(text, msg) {{
      navigator.clipboard.writeText(text).then(() => {{
        showToast(msg || "Copied: " + text);
      }}).catch(err => {{
        console.error("Failed to copy", err);
      }});
    }}

    function toggleAnalytics() {{
      const content = document.getElementById("analyticsContent");
      const btn = document.getElementById("analyticsToggleBtn");
      isAnalyticsVisible = !isAnalyticsVisible;
      if (isAnalyticsVisible) {{
        content.style.display = "grid";
        btn.innerText = "▾ Hide Overview";
      }} else {{
        content.style.display = "none";
        btn.innerText = "▸ Show Overview";
      }}
    }}

    function setPrimaryFilter(filter) {{
      currentFilter = filter;
      document.querySelectorAll("#statusFilterPills .pill").forEach(p => {{
        p.classList.toggle("active", p.getAttribute("data-filter") === filter);
      }});
      
      const stagedSub = document.getElementById("stagedSubNav");
      if (currentFilter === "staged") {{
        stagedSub.style.display = "flex";
      }} else {{
        stagedSub.style.display = "none";
      }}

      renderAll();
    }}

    function setScoreTierFilter(tier) {{
      currentScoreTier = tier;
      document.querySelectorAll("#scoreFilterPills .pill").forEach(p => {{
        p.classList.toggle("active", p.getAttribute("data-score") === tier);
      }});
      renderAll();
    }}

    function setWorkplaceFilter(mode) {{
      currentWorkplace = mode;
      document.querySelectorAll("#workplaceFilterPills .pill").forEach(p => {{
        p.classList.toggle("active", p.getAttribute("data-workplace") === mode);
      }});
      renderAll();
    }}

    function setRegionFilter(region) {{
      selectedRegion = (selectedRegion === region) ? null : region;
      renderAll();
    }}

    function setPositionFilter(pos) {{
      selectedPosition = (selectedPosition === pos) ? null : pos;
      renderAll();
    }}

    function clearSearch() {{
      document.getElementById("searchInput").value = "";
      searchQuery = "";
      document.getElementById("searchClearBtn").style.display = "none";
      renderAll();
    }}

    function resetAllFilters() {{
      currentFilter = "all";
      currentScoreTier = "all";
      currentWorkplace = "all";
      selectedRegion = null;
      selectedPosition = null;
      searchQuery = "";
      document.getElementById("searchInput").value = "";
      document.getElementById("searchClearBtn").style.display = "none";
      document.getElementById("stagedSubNav").style.display = "none";
      document.querySelectorAll("#statusFilterPills .pill").forEach(p => {{
        p.classList.toggle("active", p.getAttribute("data-filter") === "all");
      }});
      document.querySelectorAll("#scoreFilterPills .pill").forEach(p => {{
        p.classList.toggle("active", p.getAttribute("data-score") === "all");
      }});
      document.querySelectorAll("#workplaceFilterPills .pill").forEach(p => {{
        p.classList.toggle("active", p.getAttribute("data-workplace") === "all");
      }});
      renderAll();
    }}

    function handleSortChange(sortVal) {{
      currentSort = sortVal;
      renderAll();
    }}

    // Multi-term and Boolean search matching (+ for AND, , for OR)
    function matchesSearch(job, query) {{
      if (!query || !query.trim()) return true;
      const cleanQ = query.trim().toLowerCase();

      const orClauses = cleanQ.split(',').map(s => s.trim()).filter(Boolean);
      if (orClauses.length === 0) return true;

      const kws = (job.matched_keywords || []).join(' ');
      const searchableText = [
        job.title,
        job.company,
        job.location,
        job.region_group,
        job.position_group,
        job.status,
        job.recommendation,
        job.source,
        job.short_id,
        job.id,
        job.description,
        job.reasoning,
        job.is_remote ? 'remote' : 'on-site',
        kws
      ].map(v => (v || '').toLowerCase()).join(' ');

      return orClauses.some(orClause => {{
        const andTokens = orClause.split('+').map(t => t.trim()).filter(Boolean);
        if (andTokens.length === 0) return true;
        return andTokens.every(token => searchableText.includes(token));
      }});
    }}

    function filterJobs(jobList) {{
      return jobList.filter(j => {{
        // Status filter tab
        if (currentFilter === "staged" && !j.folder_rel_path) return false;
        if (currentFilter === "queued" && (j.status !== "QUEUED" || j.folder_rel_path)) return false;
        if (currentFilter === "evaluated" && (j.status !== "EVALUATED" || j.folder_rel_path)) return false;
        if (currentFilter === "applied" && j.status !== "APPLIED") return false;
        if (currentFilter === "rejected" && j.status !== "REJECTED") return false;

        // Score tier filter
        const score = (j.score !== null && j.score !== undefined) ? j.score : 0;
        if (currentScoreTier === "high" && score < 80) return false;
        if (currentScoreTier === "mid" && (score < 60 || score >= 80)) return false;
        if (currentScoreTier === "low" && score >= 60) return false;

        // Workplace mode filter
        if (currentWorkplace === "remote" && !j.is_remote) return false;
        if (currentWorkplace === "onsite" && j.is_remote) return false;

        // Region filter
        if (selectedRegion && j.region_group !== selectedRegion) return false;

        // Position filter
        if (selectedPosition && j.position_group !== selectedPosition) return false;

        // Search query
        if (searchQuery && !matchesSearch(j, searchQuery)) return false;

        return true;
      }});
    }}

    function sortJobs(jobList) {{
      return [...jobList].sort((a, b) => {{
        if (currentSort === "date_desc") {{
          return (b.discovered_ts || 0) - (a.discovered_ts || 0);
        }} else if (currentSort === "date_asc") {{
          return (a.discovered_ts || 0) - (b.discovered_ts || 0);
        }} else if (currentSort === "score_desc") {{
          return (b.score || 0) - (a.score || 0);
        }} else if (currentSort === "title_asc") {{
          return (a.title || "").localeCompare(b.title || "");
        }} else if (currentSort === "title_desc") {{
          return (b.title || "").localeCompare(a.title || "");
        }} else if (currentSort === "company_asc") {{
          return (a.company || "").localeCompare(b.company || "");
        }}
        return 0;
      }});
    }}

    function renderAnalytics() {{
      // 1. Fit Score Breakdown Donut (High 80+, Mid 60-79, Low <60)
      const highCount = JOBS.filter(j => (j.score || 0) >= 80).length;
      const midCount = JOBS.filter(j => (j.score || 0) >= 60 && (j.score || 0) < 80).length;
      const lowCount = JOBS.filter(j => (j.score || 0) < 60).length;
      const total = JOBS.length || 1;

      const highPct = ((highCount / total) * 100).toFixed(0);
      const midPct = ((midCount / total) * 100).toFixed(0);
      const lowPct = ((lowCount / total) * 100).toFixed(0);

      const circumference = 2 * Math.PI * 38;
      const highStroke = (highCount / total) * circumference;
      const midStroke = (midCount / total) * circumference;
      const lowStroke = (lowCount / total) * circumference;

      const donutHtml = `
        <svg class="donut-svg" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="transparent" stroke="#e2e8f0" stroke-width="14" />
          <circle cx="50" cy="50" r="38" fill="transparent" stroke="#059669" stroke-width="14"
            stroke-dasharray="${{highStroke}} ${{circumference}}" stroke-dashoffset="0" style="transition: stroke-dasharray 0.3s;" />
          <circle cx="50" cy="50" r="38" fill="transparent" stroke="#d97706" stroke-width="14"
            stroke-dasharray="${{midStroke}} ${{circumference}}" stroke-dashoffset="-${{highStroke}}" style="transition: stroke-dasharray 0.3s;" />
          <circle cx="50" cy="50" r="38" fill="transparent" stroke="#94a3b8" stroke-width="14"
            stroke-dasharray="${{lowStroke}} ${{circumference}}" stroke-dashoffset="-${{highStroke + midStroke}}" style="transition: stroke-dasharray 0.3s;" />
        </svg>
        <div class="donut-legend">
          <div class="donut-legend-item ${{currentScoreTier === 'high' ? 'active' : ''}}" onclick="setScoreTierFilter('${{currentScoreTier === 'high' ? 'all' : 'high'}}')">
            <span class="legend-color-dot" style="background: #059669;"></span>
            <span>High Fit (80%+): <strong>${{highCount}}</strong> (${{highPct}}%)</span>
          </div>
          <div class="donut-legend-item ${{currentScoreTier === 'mid' ? 'active' : ''}}" onclick="setScoreTierFilter('${{currentScoreTier === 'mid' ? 'all' : 'mid'}}')">
            <span class="legend-color-dot" style="background: #d97706;"></span>
            <span>Review (60-79%): <strong>${{midCount}}</strong> (${{midPct}}%)</span>
          </div>
          <div class="donut-legend-item ${{currentScoreTier === 'low' ? 'active' : ''}}" onclick="setScoreTierFilter('${{currentScoreTier === 'low' ? 'all' : 'low'}}')">
            <span class="legend-color-dot" style="background: #94a3b8;"></span>
            <span>Low / Filtered (&lt;60%): <strong>${{lowCount}}</strong> (${{lowPct}}%)</span>
          </div>
        </div>
      `;
      document.getElementById("fitDonutContainer").innerHTML = donutHtml;

      // 2. Dynamic Geographical Regions
      const regionCounts = {{}};
      JOBS.forEach(j => {{
        const r = j.region_group || "Unspecified";
        regionCounts[r] = (regionCounts[r] || 0) + 1;
      }});
      const sortedRegions = Object.entries(regionCounts).sort((a, b) => b[1] - a[1]);
      const maxRegionVal = sortedRegions.length ? sortedRegions[0][1] : 1;

      const regionsHtml = sortedRegions.map(([r, cnt]) => {{
        const pct = ((cnt / maxRegionVal) * 100).toFixed(0);
        const isActive = selectedRegion === r;
        return `
          <div class="chart-row ${{isActive ? 'active' : ''}}" onclick="setRegionFilter('${{r.replace(/'/g, "\\\'")}}')">
            <div class="chart-row-bar" style="width: ${{pct}}%;"></div>
            <div class="chart-row-content">
              <span class="chart-row-label">📍 ${{r}}</span>
              <span class="chart-row-val">${{cnt}} jobs</span>
            </div>
          </div>
        `;
      }}).join("");
      document.getElementById("regionsChartList").innerHTML = regionsHtml;

      // 3. Dynamic Position Groupings
      const posCounts = {{}};
      JOBS.forEach(j => {{
        const p = j.position_group || "Specialized Technical";
        posCounts[p] = (posCounts[p] || 0) + 1;
      }});
      const sortedPos = Object.entries(posCounts).sort((a, b) => b[1] - a[1]);
      const maxPosVal = sortedPos.length ? sortedPos[0][1] : 1;

      const posHtml = sortedPos.map(([p, cnt]) => {{
        const pct = ((cnt / maxPosVal) * 100).toFixed(0);
        const isActive = selectedPosition === p;
        return `
          <div class="chart-row ${{isActive ? 'active' : ''}}" onclick="setPositionFilter('${{p.replace(/'/g, "\\\'")}}')">
            <div class="chart-row-bar" style="width: ${{pct}}%;"></div>
            <div class="chart-row-content">
              <span class="chart-row-label">💼 ${{p}}</span>
              <span class="chart-row-val">${{cnt}} jobs</span>
            </div>
          </div>
        `;
      }}).join("");
      document.getElementById("positionsChartList").innerHTML = posHtml;

      // 4. Status Breakdown
      const statusCounts = {{
        "Staged Packages": JOBS.filter(j => j.folder_rel_path).length,
        "Queued (Ready)": JOBS.filter(j => j.status === "QUEUED" && !j.folder_rel_path).length,
        "Evaluated (Manual Review)": JOBS.filter(j => j.status === "EVALUATED" && !j.folder_rel_path).length,
        "Applied": JOBS.filter(j => j.status === "APPLIED").length,
        "Rejected": JOBS.filter(j => j.status === "REJECTED").length,
      }};
      const statusFilters = {{
        "Staged Packages": "staged",
        "Queued (Ready)": "queued",
        "Evaluated (Manual Review)": "evaluated",
        "Applied": "applied",
        "Rejected": "rejected",
      }};

      const statusHtml = Object.entries(statusCounts).map(([st, cnt]) => {{
        const fKey = statusFilters[st];
        const isActive = currentFilter === fKey;
        const pct = ((cnt / total) * 100).toFixed(0);
        return `
          <div class="chart-row ${{isActive ? 'active' : ''}}" onclick="setPrimaryFilter('${{fKey}}')">
            <div class="chart-row-bar" style="width: ${{pct}}%;"></div>
            <div class="chart-row-content">
              <span class="chart-row-label">${{st}}</span>
              <span class="chart-row-val">${{cnt}}</span>
            </div>
          </div>
        `;
      }}).join("");
      document.getElementById("statusChartList").innerHTML = statusHtml;
    }}

    function renderActiveFilterTags() {{
      const container = document.getElementById("activeFilterTags");
      const tags = [];

      if (currentScoreTier !== "all") {{
        const sLabel = currentScoreTier === "high" ? "High Fit (80%+)" : (currentScoreTier === "mid" ? "Review (60-79%)" : "Low Fit (<60%)");
        tags.push(`<span class="active-filter-tag">⭐ Match: ${{sLabel}} <span class="tag-remove" onclick="setScoreTierFilter('all')">✕</span></span>`);
      }}
      if (currentWorkplace !== "all") {{
        const wLabel = currentWorkplace === "remote" ? "Remote Only" : "On-site / Hybrid";
        tags.push(`<span class="active-filter-tag">🌐 Mode: ${{wLabel}} <span class="tag-remove" onclick="setWorkplaceFilter('all')">✕</span></span>`);
      }}
      if (selectedRegion) {{
        tags.push(`<span class="active-filter-tag">📍 Region: ${{selectedRegion}} <span class="tag-remove" onclick="setRegionFilter('${{selectedRegion.replace(/'/g, "\\\'")}}')">✕</span></span>`);
      }}
      if (selectedPosition) {{
        tags.push(`<span class="active-filter-tag">💼 Role: ${{selectedPosition}} <span class="tag-remove" onclick="setPositionFilter('${{selectedPosition.replace(/'/g, "\\\'")}}')">✕</span></span>`);
      }}
      if (searchQuery) {{
        tags.push(`<span class="active-filter-tag">🔍 Search: "${{searchQuery}}" <span class="tag-remove" onclick="clearSearch()">✕</span></span>`);
      }}

      if (tags.length > 0 || currentFilter !== "all" || currentScoreTier !== "all" || currentWorkplace !== "all") {{
        tags.push(`<button class="btn-reset-filters" onclick="resetAllFilters()">Reset All Filters</button>`);
      }}

      container.innerHTML = tags.join("");
    }}

    function renderJobs() {{
      const grid = document.getElementById("jobsGrid");
      const filtered = filterJobs(JOBS);
      const sorted = sortJobs(filtered);

      const countBar = document.getElementById("resultsCountBar");
      countBar.innerText = `Showing ${{sorted.length}} of ${{JOBS.length}} jobs`;

      if (sorted.length === 0) {{
        let helpMsg = "No job listings match the current filters.";
        if (searchQuery && (currentFilter !== "all" || currentScoreTier !== "all" || currentWorkplace !== "all")) {{
          const allMatches = JOBS.filter(j => matchesSearch(j, searchQuery));
          if (allMatches.length > 0) {{
            helpMsg += ` Found ${{allMatches.length}} match(es) in other categories! <button class="btn btn-primary" style="margin-left: 8px;" onclick="resetAllFilters()">View in All Tabs</button>`;
          }}
        }}
        grid.innerHTML = `
          <div class="empty-state">
            <p>${{helpMsg}}</p>
            <button class="btn" style="margin-top: 12px;" onclick="resetAllFilters()">Clear All Filters</button>
          </div>
        `;
        return;
      }}

      grid.innerHTML = sorted.map(j => {{
        let statusBadgeClass = "badge-discovered";
        if (j.status === "QUEUED") statusBadgeClass = "badge-queued";
        else if (j.status === "EVALUATED") statusBadgeClass = "badge-evaluated";
        else if (j.status === "APPLIED") statusBadgeClass = "badge-applied";
        else if (j.status === "REJECTED") statusBadgeClass = "badge-rejected";

        let scoreBadgeHtml = "";
        if (j.score !== null && j.score !== undefined) {{
          const sClass = j.score >= 80 ? "score-high" : (j.score >= 60 ? "score-mid" : "score-low");
          scoreBadgeHtml = `<span class="score-badge ${{sClass}}">Score: ${{j.score.toFixed(0)}}/100 (${{j.recommendation}})</span>`;
        }}

        // Quick action links
        let actionLinks = [];

        if (j.url && j.url !== "#") {{
          actionLinks.push(`<a class="btn btn-url" href="${{j.url}}" target="_blank" rel="noopener noreferrer">🔗 Open Job URL</a>`);
        }}

        if (j.folder_rel_path) {{
          actionLinks.push(`<a class="btn btn-folder" href="${{j.folder_rel_path}}/" target="_blank">📁 Staged Folder</a>`);
        }}

        if (j.resume_pdf_rel) {{
          actionLinks.push(`<a class="btn btn-primary" href="${{j.resume_pdf_rel}}" target="_blank">📄 Resume PDF</a>`);
        }}

        if (j.cover_pdf_rel) {{
          actionLinks.push(`<a class="btn btn-primary" href="${{j.cover_pdf_rel}}" target="_blank">✉️ Cover Letter PDF</a>`);
        }}

        if (j.details_md_rel) {{
          actionLinks.push(`<a class="btn" href="${{j.details_md_rel}}" target="_blank">📋 Job Details MD</a>`);
        }}

        if (!j.folder_rel_path) {{
          actionLinks.push(`<button class="btn btn-stage" onclick="copyToClipboard('python run.py stage ${{j.short_id}}', 'Copied: python run.py stage ${{j.short_id}}')">⚡ Copy Stage Cmd</button>`);
        }}

        actionLinks.push(`<button class="btn btn-approve" onclick="copyToClipboard('python run.py approve ${{j.short_id}}', 'Copied: python run.py approve ${{j.short_id}}')">✓ Copy Approve Cmd</button>`);
        actionLinks.push(`<button class="btn btn-reject" onclick="copyToClipboard('python run.py reject ${{j.short_id}}', 'Copied: python run.py reject ${{j.short_id}}')">✗ Copy Reject Cmd</button>`);

        const remoteBadgeHtml = j.is_remote ? `<span class="badge badge-remote">🌐 Remote</span>` : '';
        const sourceBadgeHtml = j.source ? `<span class="badge badge-source">${{j.source}}</span>` : '';

        return `
          <div class="job-card" id="job-${{j.short_id}}">
            <div class="card-header">
              <div class="card-title-group">
                <h2>${{j.title}}</h2>
                <div class="company">${{j.company}}</div>
                <div class="card-meta">
                  <span>📍 ${{j.location}} ${{j.is_remote ? '(Remote)' : ''}}</span>
                  <span>🏷️ ${{j.position_group}}</span>
                  <span>📡 Source: ${{j.source}}</span>
                  <span>🗓 Discovered: ${{j.discovered_at}}</span>
                  <span class="job-id-tag" onclick="copyToClipboard('${{j.short_id}}', 'Copied Job ID: ${{j.short_id}}')" title="Click to copy Short ID">ID: ${{j.short_id}} 📋</span>
                </div>
              </div>
              <div class="badges">
                ${{remoteBadgeHtml}}
                ${{sourceBadgeHtml}}
                <span class="badge ${{statusBadgeClass}}">${{j.status}}</span>
                ${{scoreBadgeHtml}}
              </div>
            </div>

            ${{j.reasoning ? `
              <div class="ai-rationale-box">
                <strong>AI Evaluation Rationale (${{j.recommendation}}):</strong> ${{j.reasoning}}
              </div>
            ` : ''}}

            ${{j.description ? `
              <details class="desc-accordion">
                <summary>View Job Description & Requirements</summary>
                <div class="desc-content">${{j.description}}</div>
              </details>
            ` : ''}}

            <div class="actions-bar">
              ${{actionLinks.join("")}}
            </div>
          </div>
        `;
      }}).join("");
    }}

    function renderAll() {{
      renderAnalytics();
      renderActiveFilterTags();
      renderJobs();
    }}

    const sInput = document.getElementById("searchInput");
    const clearBtn = document.getElementById("searchClearBtn");

    sInput.addEventListener("input", (e) => {{
      searchQuery = e.target.value;
      clearBtn.style.display = searchQuery ? "block" : "none";
      renderAll();
    }});

    function openSponsorModal() {{
      document.getElementById("sponsorModal").classList.add("show");
    }}
    function closeSponsorModal() {{
      document.getElementById("sponsorModal").classList.remove("show");
    }}
    function openHireModal() {{
      document.getElementById("hireModal").classList.add("show");
    }}
    function closeHireModal() {{
      document.getElementById("hireModal").classList.remove("show");
    }}

    renderAll();
  </script>

  <!-- Sponsor / Donate Modal -->
  <div class="modal-backdrop" id="sponsorModal" onclick="if(event.target===this) closeSponsorModal()">
    <div class="modal-box">
      <div class="modal-header">
        <h2>☕ Support & Sponsor ACE</h2>
        <button class="modal-close" onclick="closeSponsorModal()">&times;</button>
      </div>
      <div class="modal-body">
        <p><strong>Autonomous Career Engine (ACE)</strong> is a 100% free and open-source project created by <strong>Ahmet Halit Ünsal</strong> to empower candidates worldwide with autonomous job sourcing and AI application tailoring.</p>
        <p>If ACE helped you land interviews or saved you hundreds of hours, consider supporting ongoing development:</p>
        
        <div class="donation-links">
          <a href="https://github.com/sponsors/aunsal89" target="_blank" class="donation-btn btn-gh-sponsor">💖 GitHub Sponsors</a>
          <a href="https://buymeacoffee.com/aunsal" target="_blank" class="donation-btn btn-bmc">☕ Buy Me a Coffee</a>
        </div>

        <div class="crypto-box">
          <div style="font-weight: 600; margin-bottom: 6px; color: var(--text-main);">🪙 Direct Crypto Support</div>
          <div class="crypto-row">
            <span>USDT (TRC-20):</span>
            <button class="btn-copy-addr" onclick="copyToClipboard('TMX4i6Q6g7dF8uT1a6z3K9vXyZ1W2M4nL5', 'Copied USDT Address!')">Copy Address 📋</button>
          </div>
          <div class="crypto-row">
            <span>Bitcoin (BTC):</span>
            <button class="btn-copy-addr" onclick="copyToClipboard('bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh', 'Copied BTC Address!')">Copy Address 📋</button>
          </div>
          <div class="crypto-row">
            <span>Ethereum (ETH):</span>
            <button class="btn-copy-addr" onclick="copyToClipboard('0x71C83f7fB008A2d3A8679A814343f8B51352eB4A', 'Copied ETH Address!')">Copy Address 📋</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Hire the Creator Modal -->
  <div class="modal-backdrop" id="hireModal" onclick="if(event.target===this) closeHireModal()">
    <div class="modal-box">
      <div class="modal-header">
        <h2>💼 Hire the Creator & Architect</h2>
        <button class="modal-close" onclick="closeHireModal()">&times;</button>
      </div>
      <div class="modal-body">
        <p><strong>Ahmet Halit Ünsal</strong> is a Senior Engineering Leader, Embedded Systems Director & Quantitative Systems Architect with 15+ years of professional engineering experience.</p>
        
        <div style="background: var(--bg-surface-subtle); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle); margin: 12px 0; font-size: 13px;">
          <div style="font-weight: 700; color: var(--text-main); margin-bottom: 4px;">🚀 Core Leadership & Technical Mastery:</div>
          <ul style="padding-left: 18px; margin-top: 4px;">
            <li><strong>Engineering Leadership:</strong> Managed 30-engineer cross-functional teams, multi-team lead structures, and high-reliability product lifecycles.</li>
            <li><strong>Embedded Systems:</strong> Model-Based Design (MATLAB/Simulink), ISO 26262 ASIL D, AUTOSAR, EV Powertrains (VCU, MCU, BMS, Inverters), and PMSM motor control.</li>
            <li><strong>Quantitative Engineering:</strong> Architect of AURA (24/7 automated algorithmic trading engine, walk-forward optimization, and multi-regime risk systems).</li>
          </ul>
        </div>

        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px;">
          <a href="https://www.linkedin.com/in/ahmet-halit-unsal/" target="_blank" class="donation-btn" style="background: #0a66c2; color: #fff; flex: 1;">Connect on LinkedIn</a>
          <a href="mailto:aunsal89@gmail.com" class="donation-btn" style="background: var(--text-main); color: #fff; flex: 1;">✉ Send Direct Email</a>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""
