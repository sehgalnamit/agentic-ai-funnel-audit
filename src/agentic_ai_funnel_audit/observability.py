from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import threading
import time
from typing import Any, Iterator


@dataclass
class _NoOpCounter:
    def add(self, amount: int | float, attributes: dict[str, Any] | None = None) -> None:
        _ = amount
        _ = attributes


@dataclass
class _NoOpHistogram:
    def record(self, value: int | float, attributes: dict[str, Any] | None = None) -> None:
        _ = value
        _ = attributes


class _NoOpSpan:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = exc_type
        _ = exc
        _ = tb
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        _ = key
        _ = value


class _NoOpTracer:
    def start_as_current_span(self, name: str):
        return _NoOpSpan(name)


class Observability:
    """OpenTelemetry wrapper with graceful local fallback.

    When OpenTelemetry dependencies are unavailable, all methods become no-ops
    so local demo mode remains runnable.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configured = False
        self._enabled = False
        self._tracer = _NoOpTracer()
        self._counter_runs: Any = _NoOpCounter()
        self._counter_errors: Any = _NoOpCounter()
        self._hist_duration_ms: Any = _NoOpHistogram()
        self._hist_confidence: Any = _NoOpHistogram()
        self._hist_estimated_cost_usd: Any = _NoOpHistogram()

    def configure(self) -> None:
        with self._lock:
            if self._configured:
                return
            self._configured = True

            if os.getenv("AGENTIC_OTEL_ENABLED", "false").strip().lower() != "true":
                return

            try:
                from opentelemetry import metrics, trace  # type: ignore
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter  # type: ignore
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
                from opentelemetry.sdk.metrics import MeterProvider  # type: ignore
                from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # type: ignore
                from opentelemetry.sdk.resources import Resource  # type: ignore
                from opentelemetry.sdk.trace import TracerProvider  # type: ignore
                from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
            except Exception:
                return

            endpoint = os.getenv("AGENTIC_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
            headers = _parse_headers(os.getenv("AGENTIC_OTEL_EXPORTER_OTLP_HEADERS", ""))
            service_name = os.getenv("AGENTIC_SERVICE_NAME", "agentic-ai-funnel-audit")

            resource = Resource.create({"service.name": service_name})

            tracer_provider = TracerProvider(resource=resource)
            span_exporter = OTLPSpanExporter(endpoint=endpoint or None, headers=headers or None)
            tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
            trace.set_tracer_provider(tracer_provider)
            self._tracer = trace.get_tracer(service_name)

            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint or None, headers=headers or None)
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)
            meter = metrics.get_meter(service_name)

            self._counter_runs = meter.create_counter("agentic.audit.runs", unit="1")
            self._counter_errors = meter.create_counter("agentic.audit.errors", unit="1")
            self._hist_duration_ms = meter.create_histogram("agentic.audit.duration_ms", unit="ms")
            self._hist_confidence = meter.create_histogram("agentic.audit.confidence", unit="1")
            self._hist_estimated_cost_usd = meter.create_histogram("agentic.audit.estimated_cost_usd", unit="usd")
            self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
        self.configure()
        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span

    @contextmanager
    def timed_span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
        start = time.perf_counter()
        with self.span(name, attributes) as span:
            try:
                yield span
            except Exception:
                self._counter_errors.add(1, attributes=attributes)
                raise
            finally:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                self._hist_duration_ms.record(duration_ms, attributes=attributes)

    def record_run(self, attributes: dict[str, Any] | None = None) -> None:
        self.configure()
        self._counter_runs.add(1, attributes=attributes)

    def record_confidence(self, score: float, attributes: dict[str, Any] | None = None) -> None:
        self.configure()
        self._hist_confidence.record(score, attributes=attributes)

    def record_estimated_cost(self, cost_usd: float, attributes: dict[str, Any] | None = None) -> None:
        self.configure()
        self._hist_estimated_cost_usd.record(cost_usd, attributes=attributes)


def _parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for part in raw.split(","):
        token = part.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


observability = Observability()
