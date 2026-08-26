"""
Dynamic OpenRouter Free-Tier Router & Resilient Execution Engine.

Discovers, ranks, caches, and executes LLM calls across active free models
with two-level resilience (intra-model exponential backoff with jitter + inter-model cascading fallback).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import sys
from pathlib import Path

# Ensure package root is in sys.path when invoked directly
engine_root = Path(__file__).resolve().parent.parent.parent
if str(engine_root) not in sys.path:
    sys.path.insert(0, str(engine_root))

import random
import re
import time
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from dotenv import load_dotenv
load_dotenv(engine_root.parent / ".env")
load_dotenv(engine_root / ".env")

import httpx
from pydantic import BaseModel, Field

from src.utils.logger import console, logger

T = TypeVar("T", bound=BaseModel)

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "openrouter_free_models.json"
DEFAULT_CACHE_TTL = 21600  # 6 hours in seconds


class OpenRouterError(Exception):
    """Base exception for OpenRouter operations."""
    pass


class OpenRouterExhaustionError(OpenRouterError):
    """Raised when all candidate free models exhaust their retries."""
    pass


class OpenRouterSchemaError(OpenRouterError):
    """Raised when output cannot be parsed into the required schema after repair."""
    pass


class OpenRouterModelError(OpenRouterError):
    """Raised when a specific model execution fails."""
    pass


class OpenRouterModelInfo(BaseModel):
    """Metadata and heuristic score for an OpenRouter free model."""
    id: str
    name: str
    context_length: int = 8192
    score: float = 0.0
    pricing_prompt: str = "0"
    pricing_completion: str = "0"
    provider: str = ""


class OpenRouterModelCache(BaseModel):
    """Cached list of ranked OpenRouter free models with TTL timestamp."""
    timestamp: str
    ttl_seconds: int = DEFAULT_CACHE_TTL
    models: List[OpenRouterModelInfo] = Field(default_factory=list)


def clean_and_repair_json(raw_text: str) -> Dict[str, Any]:
    """
    Extract, sanitize, and repair JSON from raw LLM output.
    Handles markdown code blocks, conversational prefixes/suffixes,
    and trailing comma syntax errors.
    """
    cleaned = raw_text.strip()

    # 1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()

    # 2. Extract substring between first { and last } (or first [ and last ])
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            cleaned = cleaned[start_brace:end_brace + 1]

    # 3. Direct JSON load attempt
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 4. Repair: Remove trailing commas before closing braces/brackets
    repaired = re.sub(r",\s*([\]}])", r"\1", cleaned)

    # 5. Repair: Fix unescaped newlines in string literals
    repaired = re.sub(r'(?<!\\)\n', r'\\n', repaired)

    try:
        return json.loads(repaired)
    except Exception as e:
        raise OpenRouterSchemaError(f"Failed to parse or repair JSON from model output: {e}\nRaw output:\n{raw_text[:400]}") from e


def compute_model_heuristic_score(model_data: Dict[str, Any]) -> float:
    """
    Compute composite heuristic ranking score for a candidate free model:
    Score = w_ctx * log2(context_length) + w_cap * ParamTier + w_pref * ProviderReliability
    Weights: w_ctx = 0.40, w_cap = 0.40, w_pref = 0.20
    """
    mid = model_data.get("id", "").lower()
    name = model_data.get("name", "").lower()
    ctx = int(model_data.get("context_length", 8192) or 8192)

    # 1. Context Score (w_ctx = 0.40): normalized log2(context_length) on 0-10 scale
    ctx_log = math.log2(max(ctx, 1024))
    ctx_score = min(10.0, (ctx_log / 20.0) * 10.0)  # 1M ctx -> ~10, 256k -> ~9, 64k -> ~8, 8k -> ~6.5

    # 2. Parameter Capacity Score (w_cap = 0.40): 0-10 scale
    param_score = 3.5
    if any(x in mid for x in ["550b", "405b", "super", "ultra", "120b"]):
        param_score = 10.0
    elif any(x in mid for x in ["70b", "72b", "m3"]):
        param_score = 8.5
    elif any(x in mid for x in ["31b", "26b", "27b", "30b", "32b", "m2.7"]):
        param_score = 7.0
    elif any(x in mid for x in ["14b", "20b", "16b"]):
        param_score = 5.5
    elif any(x in mid for x in ["8b", "7b", "9b"]):
        param_score = 4.0

    # Bonus for reasoning, instruct, or aligned versions
    if any(x in mid or x in name for x in ["reasoning", "r1", "instruct", "-it", "thinking"]):
        param_score = min(10.0, param_score + 1.5)

    # 3. Provider / Model Family Reliability (w_pref = 0.20): 0-10 scale
    pref_score = 5.0
    if any(x in mid for x in ["nvidia/", "meta-llama/", "google/", "minimax/", "deepseek/", "qwen/"]):
        pref_score = 9.0
    elif any(x in mid for x in ["cohere/", "z-ai/", "mistralai/"]):
        pref_score = 8.0
    elif "openrouter/free" in mid:
        pref_score = 7.5
    elif any(x in mid for x in ["thinkingmachines/", "dots-studio/", "liquid/"]):
        pref_score = 6.0

    total_score = (0.40 * ctx_score) + (0.40 * param_score) + (0.20 * pref_score)
    return round(total_score, 2)


class OpenRouterManager:
    """
    Manages dynamic discovery, ranking, caching, and resilient execution
    across OpenRouter free-tier models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_path: Optional[Path] = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL
    ) -> None:
        self.api_key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
        self.cache_path = cache_path or DEFAULT_CACHE_PATH
        self.cache_ttl = cache_ttl_seconds
        self.models_endpoint = "https://openrouter.ai/api/v1/models"
        self.chat_endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def is_cache_valid(self) -> bool:
        """Check if local cache exists and is within TTL."""
        if not self.cache_path.exists():
            return False
        try:
            raw = self.cache_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            cached_time = datetime.fromisoformat(data["timestamp"])
            now = datetime.now(timezone.utc)
            age = (now - cached_time).total_seconds()
            return age < data.get("ttl_seconds", self.cache_ttl) and len(data.get("models", [])) > 0
        except Exception:
            return False

    def load_cached_models(self) -> List[OpenRouterModelInfo]:
        """Load ranked models from disk cache."""
        try:
            raw = self.cache_path.read_text(encoding="utf-8")
            cache = OpenRouterModelCache.model_validate_json(raw)
            return cache.models
        except Exception as e:
            logger.debug(f"Failed reading OpenRouter cache: {e}")
            return []

    def save_model_cache(self, models: List[OpenRouterModelInfo]) -> None:
        """Save ranked models list to local JSON cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache = OpenRouterModelCache(
                timestamp=datetime.now(timezone.utc).isoformat(),
                ttl_seconds=self.cache_ttl,
                models=models
            )
            self.cache_path.write_text(cache.model_dump_json(indent=2), encoding="utf-8")
            logger.debug(f"Saved {len(models)} ranked OpenRouter free models to {self.cache_path}")
        except Exception as e:
            logger.warning(f"Could not persist OpenRouter model cache: {e}")

    def discover_and_rank_models(
        self,
        limit: int = 6,
        force_refresh: bool = False
    ) -> List[OpenRouterModelInfo]:
        """
        Query OpenRouter's live API, filter active free models, score with composite heuristic,
        and return top N ranked models (using local cache when unexpired).
        """
        if not force_refresh and self.is_cache_valid():
            cached = self.load_cached_models()
            if cached:
                return cached[:limit]

        logger.info("Discovering and ranking active free models from OpenRouter API...")
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(self.models_endpoint)
                resp.raise_for_status()
                data = resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"Failed to fetch live models from OpenRouter: {e}. Using cached or fallback list.")
            cached = self.load_cached_models()
            if cached:
                return cached[:limit]
            return self._get_hardcoded_fallback_models()[:limit]

        # 1. Filter: Free tier, text models, context >= 8192, excluding moderation/audio previews
        exclude_patterns = ["content-safety", "clip", "preview", "audio", "embed", "moderation", "lyria"]
        candidate_models: List[Dict[str, Any]] = []

        for m in data:
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            ctx = int(m.get("context_length", 0) or 0)

            is_free = (
                mid.endswith(":free")
                or mid == "openrouter/free"
                or (str(pricing.get("prompt", "1")) == "0" and str(pricing.get("completion", "1")) == "0")
            )

            if not is_free or ctx < 8192:
                continue

            if any(pat in mid.lower() for pat in exclude_patterns):
                continue

            candidate_models.append(m)

        if not candidate_models:
            logger.warning("No candidate free models met filtering criteria; using hardcoded fallback.")
            return self._get_hardcoded_fallback_models()[:limit]

        # 2. Heuristic Scoring & Sorting
        scored_models: List[OpenRouterModelInfo] = []
        for m in candidate_models:
            score = compute_model_heuristic_score(m)
            pricing = m.get("pricing", {})
            provider = m.get("id", "").split("/")[0] if "/" in m.get("id", "") else ""
            info = OpenRouterModelInfo(
                id=m.get("id", ""),
                name=m.get("name", m.get("id", "")),
                context_length=int(m.get("context_length", 8192) or 8192),
                score=score,
                pricing_prompt=str(pricing.get("prompt", "0")),
                pricing_completion=str(pricing.get("completion", "0")),
                provider=provider
            )
            scored_models.append(info)

        # Sort descending by score
        scored_models.sort(key=lambda x: x.score, reverse=True)

        # Ensure openrouter/free router is available in the pool if present
        router_present = any(m.id == "openrouter/free" for m in scored_models[:limit])
        if not router_present:
            for m in scored_models:
                if m.id == "openrouter/free":
                    scored_models.insert(min(len(scored_models), limit - 1), m)
                    break

        # Save to cache
        self.save_model_cache(scored_models)

        return scored_models[:limit]

    def get_active_model_ids(self, limit: int = 6, force_refresh: bool = False) -> List[str]:
        """Convenience method returning ordered list of model ID strings."""
        ranked = self.discover_and_rank_models(limit=limit, force_refresh=force_refresh)
        return [m.id for m in ranked]

    def execute_with_fallback(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_schema: Optional[Type[T]] = None,
        max_models: int = 5,
        max_retries_per_model: int = 3,
        base_delay: float = 1.5,
        max_delay: float = 12.0,
        backoff_factor: float = 2.0,
        temperature: float = 0.1,
        timeout: float = 30.0
    ) -> Union[T, Dict[str, Any]]:
        """
        Execute request with two-level resilience:
        Level 1 (Intra-Model): Exponential backoff + jitter for retryable errors (429, 500, 502, 503, 504, timeout).
        Level 2 (Inter-Model): Cascading fallback to next ranked model when retries are exhausted.
        """
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not configured in environment or settings.")

        candidate_models = self.discover_and_rank_models(limit=max_models)
        if not candidate_models:
            raise OpenRouterExhaustionError("No free OpenRouter models available in pool.")

        # Standardize System Prompt to enforce strict raw JSON output
        json_directive = (
            "CRITICAL REQUIREMENT: Return ONLY a valid, raw JSON object matching the requested schema. "
            "Do NOT include markdown backticks (```json), code fences, explanations, greetings, or trailing thoughts."
        )
        effective_system_prompt = f"{system_prompt}\n\n{json_directive}" if system_prompt else json_directive

        execution_errors: List[str] = []

        # =========================================================================
        # LEVEL 2: INTER-MODEL CASCADING FALLBACK
        # =========================================================================
        for model_idx, model_info in enumerate(candidate_models, 1):
            model_id = model_info.id
            logger.debug(f"[OpenRouter Level 2] Engaging Model {model_idx}/{len(candidate_models)}: {model_id} (Score: {model_info.score})")

            # =====================================================================
            # LEVEL 1: INTRA-MODEL RETRIES WITH EXPONENTIAL BACKOFF & JITTER
            # =====================================================================
            for attempt in range(1, max_retries_per_model + 1):
                start_time = time.perf_counter()
                try:
                    raw_response = self._call_model(
                        model_id=model_id,
                        prompt=prompt,
                        system_prompt=effective_system_prompt,
                        temperature=temperature,
                        timeout=timeout
                    )
                    latency = round(time.perf_counter() - start_time, 2)

                    # Parse & Normalize JSON Output
                    parsed_dict = clean_and_repair_json(raw_response)

                    if response_schema:
                        validated_obj = self._validate_schema(parsed_dict, response_schema)
                        logger.info(f"OpenRouter success with [{model_id}] (attempt {attempt}, latency {latency}s)")
                        return validated_obj
                    else:
                        logger.info(f"OpenRouter success with [{model_id}] (attempt {attempt}, latency {latency}s)")
                        return parsed_dict

                except OpenRouterSchemaError as se:
                    latency = round(time.perf_counter() - start_time, 2)
                    err_msg = f"Model [{model_id}] returned invalid JSON (attempt {attempt}/{max_retries_per_model}): {se}"
                    logger.debug(err_msg)
                    if attempt == max_retries_per_model:
                        execution_errors.append(f"{model_id}: Schema parse error ({se})")
                        break
                    self._sleep_with_backoff(attempt, base_delay, max_delay, backoff_factor)

                except OpenRouterModelError as me:
                    latency = round(time.perf_counter() - start_time, 2)
                    err_msg = f"Model [{model_id}] failed (attempt {attempt}/{max_retries_per_model}): {me}"
                    logger.debug(err_msg)
                    if attempt == max_retries_per_model:
                        execution_errors.append(f"{model_id}: {me}")
                        break
                    self._sleep_with_backoff(attempt, base_delay, max_delay, backoff_factor)

                except Exception as unhandled:
                    latency = round(time.perf_counter() - start_time, 2)
                    err_msg = f"Unexpected error with model [{model_id}] (attempt {attempt}/{max_retries_per_model}): {unhandled}"
                    logger.debug(err_msg)
                    if attempt == max_retries_per_model:
                        execution_errors.append(f"{model_id}: {unhandled}")
                        break
                    self._sleep_with_backoff(attempt, base_delay, max_delay, backoff_factor)

            logger.warning(f"Circuit breaking model [{model_id}] after {max_retries_per_model} failed attempts. Cascading to next free model...")

        # All models exhausted
        error_summary = "; ".join(execution_errors)
        raise OpenRouterExhaustionError(
            f"All {len(candidate_models)} candidate free OpenRouter models failed. Summary: {error_summary}"
        )

    def _call_model(
        self,
        model_id: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        timeout: float
    ) -> str:
        """Single raw HTTP completion call to OpenRouter."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ahmethalitunsal.com",
            "X-Title": "Career Engine Orchestrator"
        }

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"} if not model_id.startswith("thinkingmachines") else None
        }
        # Filter None values
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(self.chat_endpoint, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise OpenRouterModelError("Response contained empty choices array")
                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        raise OpenRouterModelError("Response message content was empty")
                    return content

                elif resp.status_code in [429, 500, 502, 503, 504]:
                    raise OpenRouterModelError(f"Transient HTTP {resp.status_code}: {resp.text[:200]}")
                elif resp.status_code in [400, 401, 403, 404]:
                    raise OpenRouterModelError(f"Non-retryable HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    raise OpenRouterModelError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        except httpx.TimeoutException as te:
            raise OpenRouterModelError(f"Request timeout after {timeout}s: {te}") from te
        except (httpx.ConnectError, httpx.NetworkError) as ne:
            raise OpenRouterModelError(f"Network connectivity error: {ne}") from ne
        except OpenRouterModelError:
            raise
        except Exception as e:
            raise OpenRouterModelError(f"HTTP call failed: {e}") from e

    def _validate_schema(self, parsed_dict: Dict[str, Any], schema: Type[T]) -> T:
        """Validate parsed dict against target Pydantic schema."""
        try:
            if hasattr(schema, "model_validate"):
                return schema.model_validate(parsed_dict)
            return schema.parse_obj(parsed_dict)
        except Exception as ve:
            raise OpenRouterSchemaError(f"Pydantic schema validation error against {schema.__name__}: {ve}") from ve

    def _sleep_with_backoff(
        self,
        attempt: int,
        base_delay: float,
        max_delay: float,
        backoff_factor: float
    ) -> None:
        """Calculate exponential backoff with ±20% jitter and sleep."""
        delay = min(max_delay, base_delay * (backoff_factor ** (attempt - 1)))
        jitter = random.uniform(0.8, 1.2)
        total_sleep = round(delay * jitter, 2)
        logger.debug(f"Retrying in {total_sleep}s (attempt {attempt})...")
        time.sleep(total_sleep)

    def _get_hardcoded_fallback_models(self) -> List[OpenRouterModelInfo]:
        """Fallback static models if discovery API is unreachable."""
        fallback_ids = [
            ("nvidia/nemotron-3-super-120b-a12b:free", "NVIDIA: Nemotron 3 Super (free)", 262144, 9.4),
            ("minimax/minimax-m3:free", "MiniMax: MiniMax M3 (free)", 1048576, 9.2),
            ("google/gemma-4-31b-it:free", "Google: Gemma 4 31B (free)", 262144, 8.8),
            ("google/gemma-4-26b-a4b-it:free", "Google: Gemma 4 26B A4B (free)", 262144, 8.8),
            ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "NVIDIA: Nemotron 3 Nano Omni (free)", 256000, 8.79),
            ("minimax/minimax-m2.7:free", "MiniMax: MiniMax M2.7 (free)", 196608, 8.12),
            ("openrouter/free", "Free Models Router", 200000, 7.5),
        ]
        return [
            OpenRouterModelInfo(
                id=fid,
                name=fname,
                context_length=fctx,
                score=fscore,
                pricing_prompt="0",
                pricing_completion="0"
            )
            for fid, fname, fctx, fscore in fallback_ids
        ]


def main() -> None:
    """CLI utility for model cache refreshing and diagnostic inspection."""
    parser = argparse.ArgumentParser(description="OpenRouter Free-Tier Dynamic Router Utility")
    parser.add_argument("--refresh-cache", action="store_true", help="Force refresh of the model discovery cache")
    parser.add_argument("--list-models", action="store_true", help="Display currently ranked free models")
    parser.add_argument("--test", action="store_true", help="Run diagnostic live test execution")
    args = parser.parse_args()

    manager = OpenRouterManager()

    if args.refresh_cache:
        console.print("[bold cyan]Refreshing OpenRouter free models cache...[/bold cyan]")
        models = manager.discover_and_rank_models(limit=10, force_refresh=True)
        console.print(f"[bold green]✓ Successfully discovered and cached {len(models)} ranked models.[/bold green]")

    if args.list_models or not any([args.refresh_cache, args.test]):
        models = manager.discover_and_rank_models(limit=10)
        console.print("\n[bold magenta]Top Ranked OpenRouter Free-Tier Models:[/bold magenta]")
        for i, m in enumerate(models, 1):
            console.print(f" {i:2d}. [bold green]{m.id:<50}[/bold green] (Score: [yellow]{m.score:4.2f}[/yellow] | Ctx: {m.context_length:,} tokens | {m.name})")

    if args.test:
        console.print("\n[bold cyan]Executing live test prompt with schema validation...[/bold cyan]")

        class DiagnosticResult(BaseModel):
            engine_status: str
            model_used: str
            test_number: int
            skills_identified: List[str]

        prompt = "Analyze candidate qualifications: 15 years embedded systems, Simulink, AUTOSAR, ISO 26262 ASIL D. Return JSON with engine_status='OK', model_used='openrouter', test_number=42, and skills_identified list."
        try:
            res = manager.execute_with_fallback(
                prompt=prompt,
                response_schema=DiagnosticResult,
                max_models=3
            )
            console.print("[bold green]✓ Execution succeeded with validated schema:[/bold green]")
            console.print(res)
        except Exception as e:
            console.print(f"[bold red]✗ Execution failed: {e}[/bold red]")


if __name__ == "__main__":
    main()
