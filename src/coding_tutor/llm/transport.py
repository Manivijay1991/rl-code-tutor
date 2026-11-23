"""HTTP transport for LLM providers (standard library only).

A transport is any function `(url, body, headers, timeout) -> response JSON`. Providers take one
as a parameter, so tests and other HTTP stacks can replace `http_post_json`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

Transport = Callable[[str, dict, dict[str, str], int], dict]


class LLMError(RuntimeError):
    """The LLM endpoint could not be reached or returned an unusable response."""


def http_post_json(url: str, body: dict, headers: dict[str, str], timeout: int) -> dict:
    """POST `body` as JSON and return the decoded JSON response.

    Raises:
        LLMError: Network failure, HTTP error or non-JSON reply. The message names the URL and
            status but never the request headers (which may hold an API key).
    """
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise LLMError(f"{url} returned HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise LLMError(f"{url} is not reachable: {e.reason}") from None
    except json.JSONDecodeError:
        raise LLMError(f"{url} returned a non-JSON response") from None
