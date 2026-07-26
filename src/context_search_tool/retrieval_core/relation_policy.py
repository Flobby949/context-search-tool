"""Shared relation expansion policy values."""

from types import MappingProxyType

from context_search_tool.graph_contract import (
    GRAPH_SCORE_DECAY,
    MAX_EDGES_EXAMINED_PER_QUERY,
    MAX_EDGES_PER_SIGNAL_DIRECTION,
    MAX_FRONTIER_ENTRIES_PER_QUERY,
    MAX_GRAPH_SEED_SIGNALS,
    MAX_LEGACY_RELATION_HOPS,
    MAX_RELATION_EXPANDED_CANDIDATES,
    MAX_RESOLVED_GRAPH_HOPS,
    MAX_SIGNALS_PER_FILE,
    MAX_SIGNALS_POPPED_PER_QUERY,
    RELATION_DIRECTIONS,
    RELATION_KIND_PRIORITY,
    RELATION_WEIGHTS,
)


# Keep the public v4 aliases stable until Task 10 activates schema 5.
MAX_EXPANSION_DEPTH = MAX_LEGACY_RELATION_HOPS

# P9: final-selection quota for relation-supported results. Disabled
# pending the successor review: both paired A/B rounds rejected the
# active mechanism (see the P9 plan's implementation record).
RELATION_SLOTS_ENABLED = False
RELATION_FINAL_SLOTS = 2
RELATION_SLOT_SCAN_DEPTH = 50
MAX_EXPANSION_CANDIDATES = MAX_RELATION_EXPANDED_CANDIDATES
_MIN_RELATION_CONFIDENCE = 0.5

GRAPH_SCORE_KEYS = (
    "graph_calls_match",
    "graph_implements_match",
    "graph_uses_type_match",
    "graph_imports_match",
    "graph_routes_to_match",
    "graph_mapped_by_match",
    "graph_tests_match",
)

GRAPH_SCORE_KEY_BY_KIND = MappingProxyType(
    {
        "calls": "graph_calls_match",
        "implements": "graph_implements_match",
        "implements_method": "graph_implements_match",
        "uses_type": "graph_uses_type_match",
        "imports": "graph_imports_match",
        "routes_to": "graph_routes_to_match",
        "mapped_by": "graph_mapped_by_match",
        "tests": "graph_tests_match",
    }
)

GRAPH_REASON_BY_SCORE_KEY = MappingProxyType(
    {
        "graph_calls_match": "resolved Java method call",
        "graph_implements_match": "Spring interface implementation",
        "graph_uses_type_match": "repository-local related type",
        "graph_routes_to_match": "frontend route target",
        "graph_imports_match": "static module dependency",
        "graph_mapped_by_match": "MyBatis mapper statement",
        "graph_tests_match": "associated test module",
    }
)
