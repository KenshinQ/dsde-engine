"""Domain and configuration errors."""

from __future__ import annotations


class DsdeError(Exception):
    """Base error for DSDE."""


class ConfigValidationError(DsdeError):
    """Raised when a YAML config fails schema validation."""


class DomainValidationError(DsdeError):
    """Raised when a domain entity violates invariants (e.g. belief probs)."""


class PitQueryError(DsdeError):
    """Raised for illegal PIT / as-of queries."""


class DataImportError(DsdeError):
    """Raised when a provider payload cannot be imported."""


class MissingValuationModelError(DsdeError):
    """Raised when a real valuation adapter is required but missing.

    Must not silently fall back to SyntheticReturnEngine in non-synthetic modes.
    """
