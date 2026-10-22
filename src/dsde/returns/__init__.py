"""Conditional return engines (Phase 4)."""

from dsde.returns.adapters import StubFundamentalValuationAdapter
from dsde.returns.engine import AdapterConditionalReturnEngine, build_default_research_engine
from dsde.returns.protocol import ConditionalReturnEngine, ValuationAdapter
from dsde.returns.synthetic import SyntheticReturnEngine

__all__ = [
    "AdapterConditionalReturnEngine",
    "ConditionalReturnEngine",
    "StubFundamentalValuationAdapter",
    "SyntheticReturnEngine",
    "ValuationAdapter",
    "build_default_research_engine",
]
