class TrustedCeoAgentError(Exception):
    """Base error for failures with a stable CLI classification."""


class ContractError(TrustedCeoAgentError, ValueError):
    """Untrusted input violated a declared contract."""


class IntegrityError(TrustedCeoAgentError):
    """Stored or supplied bytes failed an integrity check."""


class RevisionConflict(TrustedCeoAgentError):
    """A compare-and-swap expected revision was stale."""

