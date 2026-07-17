"""Fail-closed accounting content-suite and account-universe contracts."""

from trusted_ceo_agent.accounting.coverage import assess_account_universe
from trusted_ceo_agent.accounting.dispatcher import (
    dispatch_accounting_suite,
    verify_accounting_execution_bundle,
)
from trusted_ceo_agent.accounting.execution import AccountingExecutionRegistry
from trusted_ceo_agent.accounting.suite import (
    assert_product_claim_allowed,
    assess_suite_readiness,
    build_machine_draft_suite,
    validate_accounting_suite,
)

__all__ = [
    "assert_product_claim_allowed",
    "AccountingExecutionRegistry",
    "assess_account_universe",
    "assess_suite_readiness",
    "build_machine_draft_suite",
    "dispatch_accounting_suite",
    "validate_accounting_suite",
    "verify_accounting_execution_bundle",
]
