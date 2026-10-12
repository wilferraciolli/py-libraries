from typing import Sequence

# Reciprocal rank fusion constant: dampens the gap between rank 1 and rank 2
# so neither list (vector, keyword) dominates the merged ranking.
RRF_K = 60


def reciprocal_rank_fusion(*rankings: Sequence[str], k: int = RRF_K) -> list[tuple[str, float]]:
    """
    Merge ranked id lists (best first) into one: each id scores
    sum(1 / (k + rank)) over the lists it appears in. Returns (id, score),
    best first; ties keep the order ids were first seen.

    The hybrid-search recipe: rank by meaning (vector matches) and by exact
    words (keyword matches), then fuse — so "java" finds both chats about the
    JVM and messages that literally say "java".

        fused = reciprocal_rank_fusion([m.id for m in vector_hits], [t.id for t in keyword_hits])
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
