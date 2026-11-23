"""Live bandit API: anonymous reward events from every student update one shared policy.

    GET  /v1/health   liveness
    GET  /v1/policy   shared success/failure counts per (confusion, miss bucket, action)
    POST /v1/events   {"events": [{"confusion", "bucket", "action", "reward"}], "client": "web/0.1"}

The browser keeps choosing actions itself (works offline); the API only pools rewards.
No student identifiers are accepted, stored or logged.
"""
