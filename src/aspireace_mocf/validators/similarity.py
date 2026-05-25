from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def max_similarity_to_sources(text: str, sources: list[str]) -> float:
    clean_sources = [s for s in sources if s.strip()]
    if not text.strip() or not clean_sources:
        return 0.0
    corpus = [text] + clean_sources
    matrix = TfidfVectorizer(ngram_range=(3, 5), analyzer="word").fit_transform(corpus)
    sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    return float(sims.max()) if len(sims) else 0.0
