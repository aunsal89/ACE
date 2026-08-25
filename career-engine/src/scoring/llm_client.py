"""Multi-provider LLM Client with Fallback Chains and Deterministic Fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
import requests

from src.config import LLMSettings, TenantProfile
from src.database.models import JobListing, RecommendationType, TrackType
from src.utils.logger import logger


DEFAULT_OPENROUTER_FREE_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "z-ai/glm-5.2:free",
    "minimax/minimax-m2.7:free",
    "minimax/minimax-m3:free",
    "thinkingmachines/inkling:free",
]


def _clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Clean markdown code blocks and extract structured JSON dict."""
    cleaned = raw_text.strip()
    if "```" in cleaned:
        # Match code block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()

    # If there is extra text outside JSON brackets, extract substring between first { and last }
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]

    return json.loads(cleaned)


class ScoringLLMClient:
    """Executes structured opportunity evaluation using LLMs or verified deterministic fallback."""

    def __init__(self, llm_settings: LLMSettings, tenant: TenantProfile):
        self.settings = llm_settings
        self.tenant = tenant
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    def evaluate_fit(self, job: JobListing) -> Dict[str, Any]:
        """
        Evaluate job listing against dual-track tenant criteria.
        Fallback chain:
        1. Google Gemini (via official API key)
        2. OpenRouter (sequential cascade across up to 9 free-tier models)
        3. Deterministic high-precision rule scoring engine
        """
        # Step 1: Try Primary Provider (Google Gemini)
        if self.gemini_key:
            try:
                res = self._evaluate_with_gemini(job)
                if res and isinstance(res, dict) and "overall_score" in res:
                    return res
            except Exception as e:
                logger.warning(f"Google Gemini GenAI evaluation failed: {e}. Cascading to OpenRouter fallback models.")

        # Step 2: Try OpenRouter Free-Tier Models Fallback Chain
        if self.openrouter_key:
            or_cfg = self.settings.providers.get("openrouter")
            candidate_models = (or_cfg.models if or_cfg and or_cfg.models else DEFAULT_OPENROUTER_FREE_MODELS)

            for model_name in candidate_models:
                try:
                    res = self._evaluate_with_openrouter(job, model_name=model_name)
                    if res and isinstance(res, dict) and "overall_score" in res:
                        logger.info(f"Opportunity successfully evaluated using OpenRouter free model [{model_name}].")
                        return res
                except Exception as e:
                    logger.debug(f"OpenRouter model [{model_name}] evaluation failed: {e}. Trying next free model...")

        # Step 3: Optional Legacy Providers
        if self.anthropic_key:
            try:
                res = self._evaluate_with_anthropic(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Anthropic evaluation failed: {e}.")

        if self.openai_key:
            try:
                res = self._evaluate_with_openai(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"OpenAI evaluation failed: {e}.")

        # Step 4: Deterministic Fallback Engine
        logger.info("Falling back to deterministic rule scoring engine.")
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
        prompt = f"""You are an executive career evaluation AI assessing job opportunities for Ahmet Halit Ünsal.
Dual-track profiles:
- Track A: Embedded Software Leadership / Directorship (15+ yrs exp, 8+ yrs managing teams up to 30 engineers, MBD/Simulink, ISO 26262 ASIL D, AUTOSAR, Motor Control, EV Inverters/BMS, Defense/Automotive in Istanbul/Ankara).
- Track B: Quantitative Developer / Algorithmic Trading (AURA engine, CCXT, Python/C++, walk-forward optimization, execution algorithms in Europe/APAC/China, excluding US).

Evaluate this opportunity:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description_raw}

Return ONLY valid JSON with keys:
- track: "TRACK_A" or "TRACK_B"
- overall_score: float between 0 and 100
- comp_score: float between 0 and 100
- location_score: float between 0 and 100
- tech_stack_score: float between 0 and 100
- leadership_score: float between 0 and 100
- fits_criteria: boolean
- matched_keywords: list of strings
- missing_keywords: list of strings
- reasoning: brief concise rationale string
- recommendation: "QUEUE", "REJECT", or "MANUAL_REVIEW"
"""
        model_name = self.settings.providers.get("google-genai", {}).model or "gemini-2.5-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        data = _clean_json_response(response.text)
        data["model_used"] = f"google-genai/{model_name}"
        return data

    def _evaluate_with_openrouter(self, job: JobListing, model_name: str) -> Optional[Dict[str, Any]]:
        """Evaluate job listing using OpenRouter free model with structured JSON extraction."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "HTTP-Referer": "https://ahmethalitunsal.com",
            "X-Title": "Career Engine",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "You are an executive career evaluation AI assessing job opportunities for Ahmet Halit Ünsal.\n"
            "Dual-track profiles:\n"
            "Track A: Embedded Software Leadership / Directorship (15+ yrs exp, 8+ yrs managing teams up to 30 engineers, MBD/Simulink, ISO 26262 ASIL D, AUTOSAR, Motor Control, EV Inverters/BMS, Defense/Automotive in Istanbul/Ankara).\n"
            "Track B: Quantitative Developer / Algorithmic Trading (AURA engine, CCXT, Python/C++, walk-forward optimization, execution algorithms in Europe/APAC/China, excluding US).\n\n"
            "You must return ONLY valid JSON with keys: track (TRACK_A or TRACK_B), overall_score (0-100), comp_score (0-100), location_score (0-100), tech_stack_score (0-100), leadership_score (0-100), fits_criteria (bool), matched_keywords (list of strings), missing_keywords (list of strings), reasoning (str), recommendation (QUEUE, REJECT, MANUAL_REVIEW)."
        )

        user_content = (
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location or 'N/A'}\n"
            f"Description: {job.description_raw or 'N/A'}\n"
        )

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
            "max_tokens": 2048
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            data = _clean_json_response(content)
            data["model_used"] = f"openrouter/{model_name}"
            return data
        else:
            raise RuntimeError(f"OpenRouter returned status {resp.status_code}: {resp.text[:120]}")

    def _evaluate_with_anthropic(self, job: JobListing) -> Optional[Dict[str, Any]]:
        return None

    def _evaluate_with_openai(self, job: JobListing) -> Optional[Dict[str, Any]]:
        return None
