"""Errors raised by the historical data pipeline."""

from __future__ import annotations


class DataPipelineError(Exception):
    """Base class for historical data pipeline failures."""


class SourceFormatError(DataPipelineError):
    """A provider file or response does not have the documented format."""


class SourceIntegrityError(DataPipelineError):
    """A downloaded file does not match the provider's published checksum."""


class MissingSourceFileError(DataPipelineError):
    """A required provider file is not available (locally in offline mode, or remotely)."""


class DatasetExistsError(DataPipelineError):
    """The target dataset already exists; use a new version or --force."""


class DatasetNotReadyError(DataPipelineError):
    """The dataset failed validation and is not research-ready."""


class DatasetExpiredError(DataPipelineError):
    """An ephemeral (CoinGecko) cache is older than its permitted retention."""


class DatasetIntegrityError(DataPipelineError):
    """Stored files do not match the hashes recorded in the manifest."""


class PersistenceDisabledError(DataPipelineError):
    """Storing this provider's data is disabled for compliance reasons."""
