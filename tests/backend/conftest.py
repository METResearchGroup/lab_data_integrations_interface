"""Keeps a local .env's Grafana token from exporting test spans."""

import os

from backend.telemetry.constants import AUTH_TOKEN_VARIABLE

# Set before any test imports backend.main; load_dotenv never overrides it.
os.environ[AUTH_TOKEN_VARIABLE] = ""
