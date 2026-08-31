"""
Resilient HTTP Client Utility with Exponential Backoff and Randomized Jitter.
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional, Tuple
import httpx

from src.utils.logger import logger

DEFAULT_RETRY_STATUSES: Tuple[int, ...] = (429, 500, 502, 503, 504)


def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 15.0,
    backoff_factor: float = 2.0,
    timeout: float = 35.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Any] = None,
    data: Optional[Any] = None,
    follow_redirects: bool = True,
    retry_statuses: Tuple[int, ...] = DEFAULT_RETRY_STATUSES,
) -> httpx.Response:
    """
    Execute HTTP request with robust exponential backoff and ±20% jitter.
    Retries on network errors, timeouts, and transient HTTP status codes.
    """
    last_exception: Optional[Exception] = None
    last_response: Optional[httpx.Response] = None

    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=follow_redirects, headers=headers) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                )
                last_response = response

                if response.status_code not in retry_statuses:
                    return response

                # Transient HTTP error: log and backoff
                logger.warning(
                    f"HTTP {method.upper()} {url} returned transient status {response.status_code} "
                    f"(attempt {attempt}/{max_retries})."
                )

        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
            last_exception = exc
            logger.warning(
                f"HTTP {method.upper()} {url} failed with {type(exc).__name__}: {exc} "
                f"(attempt {attempt}/{max_retries})."
            )

        if attempt < max_retries:
            delay = min(max_delay, base_delay * (backoff_factor ** (attempt - 1)))
            jitter = random.uniform(0.8, 1.2)
            total_sleep = round(delay * jitter, 2)
            logger.debug(f"Retrying in {total_sleep}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(total_sleep)

    if last_response is not None:
        return last_response

    if last_exception is not None:
        raise last_exception

    raise RuntimeError(f"Failed to execute request to {url} after {max_retries} attempts.")
