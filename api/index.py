"""Vercel entry point: the live bandit API as one serverless WSGI function.

vercel.json rewrites /api/* here; the app strips the /api prefix itself. Storage is the hosted Redis store
(coding_tutor.live.stores.redis), configured only from environment variables (KV_REST_API_URL and
KV_REST_API_TOKEN from Vercel's Upstash integration). The page and the API share one origin, so CORS is not
needed; CODING_TUTOR_ALLOWED_ORIGINS (comma-separated) allows other origins if you ever split them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from coding_tutor.engine.rules import load_tables
from coding_tutor.live.app import WSGIApp, caps_from_env, make_app
from coding_tutor.live.policy import known_confusions
from coding_tutor.live.stores.redis import store_from_env


def build_app(env: Mapping[str, str]) -> WSGIApp:
    """Build the API from the environment: the hosted store, extra CORS origins, and the daily caps.

    Events are accepted only from this site (or an allowed origin) and within the daily caps
    (CODING_TUTOR_DAILY_ARM_CAP, CODING_TUTOR_DAILY_TOTAL_CAP; defaults 50 and 5000).
    """
    origins = [o.strip() for o in env.get("CODING_TUTOR_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return make_app(
        None, known_confusions(load_tables()), origins, store=store_from_env(env),
        check_same_site=True, caps=caps_from_env(env),
    )  # fmt: skip


app = build_app(os.environ)
