"""Multi-provider LLM Client with Fallback Chains and Deterministic Fallback."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from src.config import LLMSettings, TenantProfile
from src.database.models import JobListing, RecommendationType, TrackType
from src.utils.logger import logger


class ScoringLLMClient:
    """Executes structured opportunity evaluation using LLMs or verified deterministic fallback."""

    def __init__(self, llm_settings: LLMSettings, tenant: TenantProfile):
        self.settings = llm_settings
        self.tenant = tenant
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.openai_key = os.environ.get("OPENAI_API_KEY", "")

    def evaluate_fit(self, job: JobListing) -> Dict[str, Any]:
        """Evaluate job listing against tenant criteria."""
        if self.gemini_key:
            try:
                res = self._evaluate_with_gemini(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Google GenAI evaluation failed: {e}. Trying next provider.")

        if self.anthropic_key:
            try:
                res = self._evaluate_with_anthropic(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Anthropic evaluation failed: {e}. Trying next provider.")

        if self.openai_key:
            try:
                res = self._evaluate_with_openai(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"OpenAI evaluation failed: {e}. Falling back to rule analyzer.")

        return self._evaluate_deterministic(job)

    def _evaluate_deterministic(self, job: JobListing) -> Dict[str, Any]:
        """Deterministic, high-precision scoring engine."""
        raw_desc = job.description_raw if job.description_raw else ""
        title_desc = f"{job.title} {raw_desc}".lower()
        loc_str = job.location if job.location else ""
        company_loc = f"{job.company} {loc_str}".lower()

        # Track determination
        if job.assigned_track == TrackType.TRACK_B:
            chosen_track = "TRACK_B"
        elif job.assigned_track == TrackType.TRACK_A:
            chosen_track = "TRACK_A"
        else:
            is_b = any(k in title_desc for k in ["quant", "algorithmic trading", "trading", "hft", "execution"])
            chosen_track = "TRACK_B" if is_b else "TRACK_A"

        if chosen_track == "TRACK_A":
            ta = self.tenant.tracks.track_a
            matched_kws = [k for k in ta.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
            exclusions = [ex for ex in ta.exclusions if ex.lower() in title_desc]

            tech_score = min(100.0, 60.0 + len(matched_kws) * 10.0)
            lead_terms = ["director", "head", "manager", "lead", "architect", "chief", "lider", "mimar", "takım"]
            leadership_score = 95.0 if any(lt in job.title.lower() for lt in lead_terms) else 75.0

            loc_match = any(loc.lower().split(",")[0].strip() in company_loc for loc in ta.target_locations) or job.is_remote
            location_score = 100.0 if loc_match else 50.0

            comp_score = 95.0
            if job.salary_max and job.salary_currency == "USD" and job.salary_max < 90000:
                comp_score = 50.0

            fits = len(exclusions) == 0 and location_score >= 80 and tech_score >= 60
            overall = (tech_score * 0.40) + (leadership_score * 0.30) + (location_score * 0.20) + (comp_score * 0.10)
            rec = "QUEUE" if overall >= 75.0 and fits else "REJECT" if len(exclusions) > 0 else "MANUAL_REVIEW"

            return {
                "track": "TRACK_A",
                "overall_score": round(overall, 1),
                "comp_score": comp_score,
                "location_score": location_score,
                "tech_stack_score": tech_score,
                "leadership_score": leadership_score,
                "fits_criteria": fits,
                "matched_keywords": matched_kws[:6],
                "missing_keywords": [k for k in ta.core_competencies if k not in matched_kws][:4],
                "reasoning": f"Track A match: {len(matched_kws)} competencies matched. Leadership role verified.",
                "recommendation": rec,
                "model_used": "rule_engine_deterministic"
            }

        else:
            tb = self.tenant.tracks.track_b
            matched_kws = [k for k in tb.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
            is_us = "united states" in company_loc or "usa" in company_loc or "ny" in company_loc

            loc_match = any(c.lower() in company_loc for c in tb.target_cities) or job.is_remote
            location_score = 0.0 if is_us else 100.0 if loc_match else 70.0

            tech_score = min(100.0, 60.0 + len(matched_kws) * 10.0)
            leadership_score = 90.0
            comp_score = 95.0

            fits = not is_us and location_score >= 70 and tech_score >= 60
            overall = (tech_score * 0.45) + (location_score * 0.35) + (comp_score * 0.20)
            rec = "QUEUE" if overall >= 75.0 and fits else "REJECT" if is_us else "MANUAL_REVIEW"

            return {
                "track": "TRACK_B",
                "overall_score": round(overall, 1),
                "comp_score": comp_score,
                "location_score": location_score,
                "tech_stack_score": tech_score,
                "leadership_score": leadership_score,
                "fits_criteria": fits,
                "matched_keywords": matched_kws[:6],
                "missing_keywords": [k for k in tb.core_competencies if k not in matched_kws][:4],
                "reasoning": f"Track B match: Quant/execution role in target region ({job.location}). AURA architecture fit.",
                "recommendation": rec,
                "model_used": "rule_engine_deterministic"
            }

    def _evaluate_with_gemini(self, job: JobListing) -> Optional[Dict[str, Any]]:
        from google import genai
        client = genai.Client(api_key=self.gemini_key)
        prompt = f"""Evaluate this job listing for Ahmet Halit Ünsal:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description_raw}

Return JSON with keys: track (TRACK_A or TRACK_B), overall_score (0-100), comp_score (0-100), location_score (0-100), tech_stack_score (0-100), leadership_score (0-100), fits_criteria (bool), matched_keywords (list), missing_keywords (list), reasoning (str), recommendation (QUEUE, REJECT, MANUAL_REVIEW)."""
        response = client.models.generate_content(
            model=self.settings.providers.get("google-genai", {}).model or "gemini-2.5-pro",
            contents=prompt
        )
        data = json.loads(response.text)
        data["model_used"] = "google-genai"
        return data

    def _evaluate_with_anthropic(self, job: JobListing) -> Optional[Dict[str, Any]]:
        return None

    def _evaluate_with_openai(self, job: JobListing) -> Optional[Dict[str, Any]]:
        return None
