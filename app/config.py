"""Runtime configuration.

The Gemini API key is retrieved from Google Cloud Secret Manager (mandatory
hackathon requirement). A process env var is honoured only for local dev and
must never be committed.
"""

import os
from functools import lru_cache

SECRET_ID = "gemini-api-key"


def _project_id() -> str | None:
    return os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")


@lru_cache(maxsize=1)
def get_gemini_api_key() -> str | None:
    """Secret Manager is the source of truth; env var only when no project is set
    (local dev without cloud access). Never read from committed files."""
    project = _project_id()
    if project:
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project}/secrets/{SECRET_ID}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("utf-8")
        except Exception:
            return None
    return os.environ.get("GEMINI_API_KEY")


def get_firebase_web_config() -> dict | None:
    """Public Firebase web-app config (apiKey etc. are not secrets), from env."""
    import json

    raw = os.environ.get("FIREBASE_WEB_CONFIG")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
