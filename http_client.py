from __future__ import annotations

from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import DEFAULT_SETTINGS, Settings


def create_session(settings: Settings = DEFAULT_SETTINGS) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": settings.user_agent})
    retries = Retry(
        total=settings.retries,
        backoff_factor=settings.backoff_factor,
        status_forcelist=list(settings.retry_statuses),
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


SESSION = create_session()


def get_session(custom: Optional[requests.Session] = None) -> requests.Session:
    if custom is not None:
        return custom
    return SESSION


__all__ = ["SESSION", "create_session", "get_session"]
