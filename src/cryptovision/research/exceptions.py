"""Errors raised by the research engine."""

from __future__ import annotations


class ResearchError(Exception):
    """Base class for research failures."""


class ExperimentConfigError(ResearchError):
    """An experiment configuration is missing, unreadable or invalid."""


class ProtocolIntegrityError(ResearchError):
    """The protocol or configuration no longer matches its frozen hash."""


class InsufficientSampleError(ResearchError):
    """A regime has too few observations for the estimand."""


class GateNotPassedError(ResearchError):
    """Empirical inference was requested without a valid simulation gate result."""


class ArtifactError(ResearchError):
    """A result bundle is missing, inconsistent or would be overwritten."""
