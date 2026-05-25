"""Tests for validators/similarity.py — TF-IDF source-similarity cache."""
from __future__ import annotations

import pytest

from aspireace_mocf.validators.similarity import SourceSimilarityCache, max_similarity_to_sources


SOURCE = (
    "Dimensions show how a physical quantity depends on mass, length and time. "
    "Velocity has dimension [LT^-1]. Force has dimension [MLT^-2]. "
    "Dimensional analysis can check the consistency of an equation."
)


def test_empty_sources_returns_zero():
    cache = SourceSimilarityCache([])
    assert cache.max_similarity("any text") == 0.0


def test_empty_text_returns_zero():
    cache = SourceSimilarityCache([SOURCE])
    assert cache.max_similarity("") == 0.0
    assert cache.max_similarity("   ") == 0.0


def test_identical_text_high_similarity():
    cache = SourceSimilarityCache([SOURCE])
    sim = cache.max_similarity(SOURCE)
    assert sim > 0.9  # near-identical, but TF-IDF over ngrams may not be exactly 1.0


def test_unrelated_text_low_similarity():
    cache = SourceSimilarityCache([SOURCE])
    sim = cache.max_similarity(
        "The mitochondria is the powerhouse of the cell. Eukaryotic cells "
        "differ from prokaryotic ones in their membrane-bound organelles."
    )
    assert sim < 0.3


def test_partial_overlap_moderate_similarity():
    cache = SourceSimilarityCache([SOURCE])
    sim = cache.max_similarity(
        "Dimensional analysis checks equation consistency. Mass, length, time."
    )
    # Some signature words match (mass, length, time, dimensional analysis), so
    # similarity should be moderate (> 0 but < high-copy threshold).
    assert 0.0 < sim < 0.95


def test_max_similarity_to_sources_legacy_api():
    """Backward-compat wrapper still works."""
    sim = max_similarity_to_sources(SOURCE, [SOURCE])
    assert sim > 0.9


def test_cache_reused_across_multiple_records():
    """The whole point of the cache: build vectorizer once, transform many."""
    cache = SourceSimilarityCache([SOURCE])
    sims = [
        cache.max_similarity("Dimensional analysis is helpful."),
        cache.max_similarity("Force equals mass times acceleration."),
        cache.max_similarity("Cells contain DNA."),
    ]
    # Should all return floats, no exceptions even on repeated calls.
    assert all(isinstance(s, float) for s in sims)
    # First two have keyword overlap with source; third doesn't.
    assert sims[2] < sims[0]
    assert sims[2] < sims[1]


def test_multiple_sources_returns_max():
    """If passed multiple source texts, returns max similarity across them."""
    source_a = "Force equals mass times acceleration. F = ma."
    source_b = "Quadratic formula gives roots of polynomial equations."
    cache = SourceSimilarityCache([source_a, source_b])
    # Query matches source_a almost verbatim; source_b is unrelated.
    sim = cache.max_similarity("Force equals mass times acceleration.")
    # Max similarity should be very high (matches source_a).
    assert sim > 0.7
