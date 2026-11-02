"""OpenTelemetry stub — wires TracerProvider without exporters by default."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_otel(service_name: str = "mymlfw-api") -> trace.Tracer:
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
