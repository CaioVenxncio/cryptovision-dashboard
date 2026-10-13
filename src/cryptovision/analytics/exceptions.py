"""Errors raised by analytics functions."""

from __future__ import annotations


class AnalyticsError(Exception):
    """Base class for analytics failures."""


class InvalidPriceError(AnalyticsError):
    """A price is missing, non-finite, zero or negative."""


class DuplicateObservationError(AnalyticsError):
    """The same asset has more than one observation for a timestamp."""


class IncompatibleDataError(AnalyticsError):
    """Inputs mix providers, quote currencies, frequencies or daily boundaries."""


class UnknownAssetError(AnalyticsError):
    """A requested asset is not in the data."""


class InsufficientDataError(AnalyticsError):
    """Too few observations for the requested calculation."""
