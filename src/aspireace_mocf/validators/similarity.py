"""Source-similarity validator — TF-IDF cosine against source text.

Purpose: catch LLM outputs that have copy-pasted from the source material
(rather than paraphrasing as instructed). Per `prompts/*.md` rules, factory
output must be original phrasing, not source verbatim.

Bug fixes vs v0.3.0 baseline:
- Bug #11 fix: the old function built a fresh TfidfVectorizer per call,
  meaning for N records x M source texts it did N x M vectorizations of the
  source. Now sources are precomputed once via the `SourceSimilarityCache`
  class and reused.

Above-the-bar additions:
- Cached vectorizer scoped per source-corpus so verifying 100 records against
  one source costs ~1 fit + 100 transforms instead of 100 full fits.
- Optional sentence-embedding upgrade path (not wired in M1 but documented in
  the class docstring).

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
SLA: verify one lane of 100 records against a 5K-word source: <= 5 seconds.
"""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class SourceSimilarityCache:
    """Per-source-corpus TF-IDF cache.

    Build once per pipeline run (per source corpus); reuse for every record
    verification in that run.

    Future M3+ upgrade path: swap TF-IDF for sentence-embedding cosine via
    sentence-transformers. Same interface; just better signal. Out of M1 scope.
    """

    def __init__(self, sources: list[str]) -> None:
        self.clean_sources = [s for s in sources if s.strip()]
        if self.clean_sources:
            # Fit on the source corpus only; record text is transformed at query time.
            # Unigrams retain a useful signal for short paraphrases, while the
            # higher-order terms still reward copied phrases over loose overlap.
            self._vectorizer = TfidfVectorizer(ngram_range=(1, 5), analyzer="word")
            self._source_vectors = self._vectorizer.fit_transform(self.clean_sources)
        else:
            self._vectorizer = None
            self._source_vectors = None

    def max_similarity(self, text: str) -> float:
        """Return max cosine similarity of `text` to any cached source.

        Returns 0.0 if no source corpus exists or text is empty.
        """
        if not self._vectorizer or self._source_vectors is None or not text.strip():
            return 0.0
        query_vec = self._vectorizer.transform([text])
        sims = cosine_similarity(query_vec, self._source_vectors).flatten()
        return float(sims.max()) if len(sims) else 0.0


def max_similarity_to_sources(text: str, sources: list[str]) -> float:
    """Backward-compatible scalar API.

    For one-off calls. For bulk verification, prefer `SourceSimilarityCache`.
    """
    cache = SourceSimilarityCache(sources)
    return cache.max_similarity(text)
