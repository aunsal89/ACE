"""
HTML Review Dashboard Generator for Career Engine staged jobs in /inbox/.
Produces a self-contained, responsive, zero-external-dependency HTML dashboard at inbox/index.html.
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

    # Also scan disk for any staged folders under track_*
    disk_folders_by_job_id: Dict[str, Path] = {}
    for track_folder in inbox_dir.glob("track_*"):
        if track_folder.is_dir():
            for item in track_folder.rglob("*"):
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

        job_cards_data.append({
            "id": job.id,
            "short_id": job.id[:8],
            "title": job.title,
            "company": job.company,
            "location": job.location or "Location Not Specified",
            "is_remote": job.is_remote,
            "track": job.assigned_track.value,
            "status": job.status.value,
            "source": job.source,
            "url": job.url or "#",
            "discovered_at": job.discovered_at.strftime("%Y-%m-%d %H:%M") if job.discovered_at else "",
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

    # Stats calculation
    total_count = len(job_cards_data)
    track_a_count = sum(1 for j in job_cards_data if j["track"] == "TRACK_A")
    track_b_count = sum(1 for j in job_cards_data if j["track"] == "TRACK_B")
    pending_count = sum(1 for j in job_cards_data if j["status"] in ("QUEUED", "EVALUATED", "DISCOVERED") and j.get("folder_rel_path"))
    approved_count = sum(1 for j in job_cards_data if j["status"] == "APPLIED")
    rejected_count = sum(1 for j in job_cards_data if j["status"] == "REJECTED")

    html_content = _build_html_template(
        tenant=tenant,
        job_cards=job_cards_data,
        stats={
            "total": total_count,
            "track_a": track_a_count,
            "track_b": track_b_count,
            "pending": pending_count,
            "approved": approved_count,
            "rejected": rejected_count,
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
    """Render self-contained HTML dashboard."""
    jobs_json = json.dumps(job_cards, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Career Engine — Opportunities & Application Review</title>
  <style>
    :root {{
      --bg-base: #0b0f17;
      --bg-card: #131b2e;
      --bg-card-hover: #1a253f;
      --border-subtle: #1e293b;
      --border-highlight: #334155;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-blue: #38bdf8;
      --accent-amber: #f59e0b;
      --accent-emerald: #10b981;
      --accent-rose: #f43f5e;
      --accent-purple: #a855f7;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }}
    body {{
      background-color: var(--bg-base);
      color: var(--text-main);
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1400px;
      margin: 0 auto;
    }}
    header {{
      background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 28px;
      margin-bottom: 24px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .header-title h1 {{
      font-size: 24px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .header-title p {{
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }}
    .time-badge {{
      font-size: 12px;
      background: rgba(56, 189, 248, 0.1);
      color: var(--accent-blue);
      border: 1px solid rgba(56, 189, 248, 0.2);
      padding: 4px 12px;
      border-radius: 20px;
    }}
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }}
    .stat-card {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 12px 16px;
      text-align: center;
    }}
    .stat-card .val {{
      font-size: 24px;
      font-weight: 700;
      color: var(--text-main);
    }}
    .stat-card .label {{
      font-size: 12px;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 2px;
    }}
    .controls {{
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
    }}
    .search-box {{
      flex: 1;
      min-width: 280px;
      position: relative;
    }}
    .search-box input {{
      width: 100%;
      background: #0f172a;
      border: 1px solid var(--border-highlight);
      color: var(--text-main);
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }}
    .search-box input:focus {{
      border-color: var(--accent-blue);
    }}
    .filter-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .pill {{
      background: #0f172a;
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      padding: 8px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .pill:hover {{
      border-color: var(--border-highlight);
      color: #fff;
    }}
    .pill.active {{
      background: var(--accent-blue);
      color: #0b0f17;
      border-color: var(--accent-blue);
      font-weight: 600;
    }}
    .jobs-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
    }}
    .job-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 20px;
      transition: transform 0.15s, border-color 0.15s;
    }}
    .job-card:hover {{
      border-color: var(--border-highlight);
      background: var(--bg-card-hover);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}
    .card-title-group h2 {{
      font-size: 18px;
      font-weight: 600;
      color: #fff;
    }}
    .card-title-group .company {{
      font-size: 15px;
      font-weight: 600;
      color: var(--accent-amber);
      margin-top: 2px;
    }}
    .card-meta {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 6px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .badges {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .badge {{
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge-track-a {{
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}
    .badge-track-b {{
      background: rgba(168, 85, 247, 0.15);
      color: var(--accent-purple);
      border: 1px solid rgba(168, 85, 247, 0.3);
    }}
    .badge-queued {{
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-blue);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .badge-applied {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-emerald);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}
    .badge-rejected {{
      background: rgba(244, 63, 94, 0.15);
      color: var(--accent-rose);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }}
    .badge-discovered {{
      background: rgba(148, 163, 184, 0.15);
      color: var(--text-muted);
      border: 1px solid rgba(148, 163, 184, 0.3);
    }}
    .score-badge {{
      font-size: 13px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 8px;
      background: #0f172a;
      border: 1px solid var(--border-highlight);
    }}
    .score-high {{ color: var(--accent-emerald); border-color: rgba(16, 185, 129, 0.4); }}
    .score-mid {{ color: var(--accent-amber); border-color: rgba(245, 158, 11, 0.4); }}
    .score-low {{ color: var(--accent-rose); border-color: rgba(244, 63, 94, 0.4); }}
    
    .actions-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--border-subtle);
      align-items: center;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 6px;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.15s;
      border: 1px solid var(--border-highlight);
      background: #0f172a;
      color: var(--text-main);
    }}
    .btn:hover {{
      background: #1e293b;
      color: #fff;
    }}
    .btn-primary {{
      background: rgba(56, 189, 248, 0.1);
      border-color: rgba(56, 189, 248, 0.4);
      color: var(--accent-blue);
    }}
    .btn-primary:hover {{
      background: rgba(56, 189, 248, 0.2);
    }}
    .btn-approve {{
      background: rgba(16, 185, 129, 0.1);
      border-color: rgba(16, 185, 129, 0.4);
      color: var(--accent-emerald);
    }}
    .btn-approve:hover {{
      background: rgba(16, 185, 129, 0.2);
    }}
    .btn-reject {{
      background: rgba(244, 63, 94, 0.1);
      border-color: rgba(244, 63, 94, 0.4);
      color: var(--accent-rose);
    }}
    .btn-reject:hover {{
      background: rgba(244, 63, 94, 0.2);
    }}
    .btn-folder {{
      background: rgba(245, 158, 11, 0.1);
      border-color: rgba(245, 158, 11, 0.4);
      color: var(--accent-amber);
    }}
    .btn-folder:hover {{
      background: rgba(245, 158, 11, 0.2);
    }}
    .btn-url {{
      background: rgba(168, 85, 247, 0.1);
      border-color: rgba(168, 85, 247, 0.4);
      color: var(--accent-purple);
    }}
    .btn-url:hover {{
      background: rgba(168, 85, 247, 0.2);
    }}
    
    .job-id-tag {{
      font-family: monospace;
      font-size: 11px;
      background: #090d16;
      border: 1px solid var(--border-subtle);
      padding: 4px 8px;
      border-radius: 4px;
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .job-id-tag:hover {{
      color: var(--accent-blue);
      border-color: var(--accent-blue);
    }}

    details.desc-accordion {{
      margin-top: 12px;
      background: #0b1120;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 8px 12px;
    }}
    details.desc-accordion summary {{
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      outline: none;
    }}
    details.desc-accordion summary:hover {{
      color: var(--text-main);
    }}
    .desc-content {{
      margin-top: 10px;
      font-size: 13px;
      color: var(--text-muted);
      white-space: pre-wrap;
      max-height: 250px;
      overflow-y: auto;
      padding-right: 8px;
      border-top: 1px solid var(--border-subtle);
      padding-top: 8px;
    }}
    .toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #10b981;
      color: #0b0f17;
      font-weight: 600;
      font-size: 13px;
      padding: 10px 18px;
      border-radius: 8px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease-in-out;
      z-index: 9999;
    }}
    .toast.show {{
      opacity: 1;
    }}
    .empty-state {{
      text-align: center;
      padding: 48px 24px;
      color: var(--text-dim);
      font-size: 16px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-top">
        <div class="header-title">
          <h1>🎯 Career Engine Review Dashboard</h1>
          <p>Tenant: <strong>{html.escape(tenant.name)}</strong> ({html.escape(tenant.tenant_id)}) &nbsp;|&nbsp; Authoritative Hub</p>
        </div>
        <div class="time-badge">Refreshed: {generated_time}</div>
      </div>
      <div class="stats-bar">
        <div class="stat-card">
          <div class="val" id="stat-total">{stats["total"]}</div>
          <div class="label">Total Sourced</div>
        </div>
        <div class="stat-card">
          <div class="val" style="color: var(--accent-amber);">{stats["track_a"]}</div>
          <div class="label">Track A (Embedded)</div>
        </div>
        <div class="stat-card">
          <div class="val" style="color: var(--accent-purple);">{stats["track_b"]}</div>
          <div class="label">Track B (Quant)</div>
        </div>
        <div class="stat-card">
          <div class="val" style="color: var(--accent-blue);">{stats["pending"]}</div>
          <div class="label">Staged / Queued</div>
        </div>
        <div class="stat-card">
          <div class="val" style="color: var(--accent-emerald);">{stats["approved"]}</div>
          <div class="label">Applied</div>
        </div>
        <div class="stat-card">
          <div class="val" style="color: var(--accent-rose);">{stats["rejected"]}</div>
          <div class="label">Rejected</div>
        </div>
      </div>
    </header>

    <div class="controls">
      <div class="search-box">
        <input type="text" id="searchInput" placeholder="Search by title, company, location, keywords, ID..." />
      </div>
      <div class="filter-pills">
        <button class="pill active" data-filter="all">All ({stats["total"]})</button>
        <button class="pill" data-filter="track_a">Track A ({stats["track_a"]})</button>
        <button class="pill" data-filter="track_b">Track B ({stats["track_b"]})</button>
        <button class="pill" data-filter="staged">Staged Packages ({stats["pending"]})</button>
        <button class="pill" data-filter="applied">Applied ({stats["approved"]})</button>
        <button class="pill" data-filter="rejected">Rejected ({stats["rejected"]})</button>
      </div>
    </div>

    <div class="jobs-grid" id="jobsGrid"></div>
  </div>

  <div id="toast" class="toast">Command copied to clipboard!</div>

  <script>
    const JOBS = {jobs_json};
    let currentFilter = "all";
    let searchQuery = "";

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

    function renderJobs() {{
      const grid = document.getElementById("jobsGrid");
      const filtered = JOBS.filter(j => {{
        // Filter pills
        if (currentFilter === "track_a" && j.track !== "TRACK_A") return false;
        if (currentFilter === "track_b" && j.track !== "TRACK_B") return false;
        if (currentFilter === "staged" && !j.folder_rel_path) return false;
        if (currentFilter === "applied" && j.status !== "APPLIED") return false;
        if (currentFilter === "rejected" && j.status !== "REJECTED") return false;

        // Search
        if (searchQuery) {{
          const q = searchQuery.toLowerCase();
          const matchTitle = (j.title || "").toLowerCase().includes(q);
          const matchCompany = (j.company || "").toLowerCase().includes(q);
          const matchLoc = (j.location || "").toLowerCase().includes(q);
          const matchId = (j.id || "").toLowerCase().includes(q) || (j.short_id || "").toLowerCase().includes(q);
          const matchDesc = (j.description || "").toLowerCase().includes(q);
          const matchReason = (j.reasoning || "").toLowerCase().includes(q);
          if (!matchTitle && !matchCompany && !matchLoc && !matchId && !matchDesc && !matchReason) {{
            return false;
          }}
        }}
        return true;
      }});

      if (filtered.length === 0) {{
        grid.innerHTML = '<div class="empty-state">No job listings found matching current filters.</div>';
        return;
      }}

      grid.innerHTML = filtered.map(j => {{
        const isTrackA = j.track === "TRACK_A";
        const trackBadgeClass = isTrackA ? "badge-track-a" : "badge-track-b";
        const trackLabel = isTrackA ? "Track A (Embedded)" : "Track B (Quant)";
        
        let statusBadgeClass = "badge-discovered";
        if (j.status === "QUEUED" || j.status === "EVALUATED") statusBadgeClass = "badge-queued";
        else if (j.status === "APPLIED") statusBadgeClass = "badge-applied";
        else if (j.status === "REJECTED") statusBadgeClass = "badge-rejected";

        let scoreBadgeHtml = "";
        if (j.score !== null && j.score !== undefined) {{
          const sClass = j.score >= 85 ? "score-high" : (j.score >= 70 ? "score-mid" : "score-low");
          scoreBadgeHtml = `<span class="score-badge ${{sClass}}">Score: ${{j.score.toFixed(0)}}/100 (${{j.recommendation}})</span>`;
        }}

        // Quick action links
        let actionLinks = [];

        // Original URL link
        if (j.url && j.url !== "#") {{
          actionLinks.push(`<a class="btn btn-url" href="${{j.url}}" target="_blank" rel="noopener noreferrer">🔗 Open Job URL</a>`);
        }}

        // Folder link (strictly relative)
        if (j.folder_rel_path) {{
          actionLinks.push(`<a class="btn btn-folder" href="${{j.folder_rel_path}}/" target="_blank">📁 Staged Folder</a>`);
        }}

        // Resume PDF
        if (j.resume_pdf_rel) {{
          actionLinks.push(`<a class="btn btn-primary" href="${{j.resume_pdf_rel}}" target="_blank">📄 Resume PDF</a>`);
        }}

        // Cover Letter PDF
        if (j.cover_pdf_rel) {{
          actionLinks.push(`<a class="btn btn-primary" href="${{j.cover_pdf_rel}}" target="_blank">✉️ Cover Letter PDF</a>`);
        }}

        // Details MD
        if (j.details_md_rel) {{
          actionLinks.push(`<a class="btn" href="${{j.details_md_rel}}" target="_blank">📋 Job Details MD</a>`);
        }}

        // Approve Command Button
        actionLinks.push(`<button class="btn btn-approve" onclick="copyToClipboard('python run.py approve ${{j.short_id}}', 'Copied: python run.py approve ${{j.short_id}}')">✓ Copy Approve Cmd</button>`);
        
        // Reject Command Button
        actionLinks.push(`<button class="btn btn-reject" onclick="copyToClipboard('python run.py reject ${{j.short_id}}', 'Copied: python run.py reject ${{j.short_id}}')">✗ Copy Reject Cmd</button>`);

        return `
          <div class="job-card" id="job-${{j.short_id}}">
            <div class="card-header">
              <div class="card-title-group">
                <h2>${{j.title}}</h2>
                <div class="company">${{j.company}}</div>
                <div class="card-meta">
                  <span>📍 ${{j.location}} ${{j.is_remote ? '(Remote)' : ''}}</span>
                  <span>📡 Source: ${{j.source}}</span>
                  <span>🗓 Discovered: ${{j.discovered_at}}</span>
                  <span class="job-id-tag" onclick="copyToClipboard('${{j.short_id}}', 'Copied Job ID: ${{j.short_id}}')" title="Click to copy Short ID">ID: ${{j.short_id}} 📋</span>
                </div>
              </div>
              <div class="badges">
                <span class="badge ${{trackBadgeClass}}">${{trackLabel}}</span>
                <span class="badge ${{statusBadgeClass}}">${{j.status}}</span>
                ${{scoreBadgeHtml}}
              </div>
            </div>

            ${{j.reasoning ? `
              <div style="font-size: 13px; color: #cbd5e1; background: rgba(15, 23, 42, 0.4); padding: 8px 12px; border-radius: 6px; border-left: 3px solid var(--accent-blue); margin-top: 8px;">
                <strong>AI Evaluation Rationale:</strong> ${{j.reasoning}}
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

    // Setup event listeners
    document.querySelectorAll(".pill").forEach(p => {{
      p.addEventListener("click", () => {{
        document.querySelectorAll(".pill").forEach(el => el.classList.remove("active"));
        p.classList.add("active");
        currentFilter = p.getAttribute("data-filter");
        renderJobs();
      }});
    }});

    const sInput = document.getElementById("searchInput");
    sInput.addEventListener("input", (e) => {{
      searchQuery = e.target.value;
      renderJobs();
    }});

    // Initial render
    renderJobs();
  </script>
</body>
</html>
"""
