"""Ingest phases: fetch a regulator artifact, stage it faithfully, promote it under the rules."""

from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment

__all__ = ["IngestRun", "open_ingest_run", "resolve_environment"]
