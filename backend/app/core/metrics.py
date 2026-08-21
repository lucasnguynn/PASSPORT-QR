"""Prometheus instrumentation and bounded-context metrics."""

from fastapi import FastAPI
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

qr_scan_total = Counter("qr_scan_total", "QR verification results", ["result"])
qr_fraud_alerts_total = Counter("qr_fraud_alerts_total", "Fraud alerts raised", ["alert_type"])
story_created_total = Counter("story_created_total", "Customer stories created")
reaction_total = Counter("reaction_total", "Story reactions created or changed")
feed_latency_seconds = Histogram("feed_latency_seconds", "Social feed generation latency")


def configure_metrics(app: FastAPI) -> None:
    """Instrument application requests and expose the Prometheus endpoint."""
    Instrumentator().instrument(app).expose(app, include_in_schema=False)
