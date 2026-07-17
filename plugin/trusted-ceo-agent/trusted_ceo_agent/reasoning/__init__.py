"""Bounded, schema-shaped reasoning utilities.

Every value accepted here is treated as untrusted until the relevant normalizer
has checked its stage allow-list and materialized runtime provenance.
"""

from trusted_ceo_agent.reasoning.jobs import build_reasoning_job, compile_stage_jobs

__all__ = ["build_reasoning_job", "compile_stage_jobs"]
