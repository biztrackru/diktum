"""Diktum's local runtime defaults, applied before importing ML libraries."""
import os

# Processing never opts into upstream usage metrics, including CLI entrypoints.
os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

__version__ = "0.2.0a2"
