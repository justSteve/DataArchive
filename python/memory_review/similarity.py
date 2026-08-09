"""Similarity backends for the memory review pipeline. [da-04r]

Ships the `lexical` adapter named in
`/root/projects/COO/docs/specs/graduation-trigger-design.md` §3.2, behind the
`SimilarityIndex` interface so the vector decision (co-ta0m) can land later
without touching anything else. `backend_name()` is stamped into every heartbeat
and packet, so a candidate is always attributable to the backend that produced it.

**What this measures, stated plainly so nobody over-reads it: aboutness.** It
finds passages on the same subject. It cannot tell agreement from contradiction —
"center the fly on the consolidation range" and "never center a fly on a range"
score as a near-identical pair, because they *are* about the same thing.
Separating those two is the reader's job, which is the entire reason this
pipeline builds a form instead of a decision.

## Why IDF-weighted token overlap, and not character trigrams

The first implementation scored character-trigram Jaccard blended with
containment. Measured against the live corpus on 2026-08-09, it failed three
ways at once, and all three had the same cause — trigram containment saturates
whenever a short text is compared to a long one, because English trigrams repeat:

| Symptom | Measurement |
|---|---|
| every memory looked anchored | 40 of 40 cards labelled "Steve stated this", including a v_down trading card matched to *"good distinctions made there. great job."* |
| contradiction ranking was flat | every concept-vs-instruction pair scored exactly 0.85 — the containment ceiling — so "ranked and capped" was picking arbitrarily |
| clustering collapsed | 214 utterances merged into 4 connected components under single-link |

Tokens with inverse-document-frequency weighting fix all three: a shared rare
word ("tombstone", "zepo", "butterfly") counts, a shared common one ("the thing
we should") does not, and length asymmetry stops mattering because the score is
a ratio of *weight*, not of counts.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Iterable, Protocol, Sequence


class SimilarityIndex(Protocol):
    """The interface an alternative backend (sqlite-vec, MemPalace) must satisfy."""

    def add(self, key: str, text: str, meta: dict | None = None) -> None: ...

    def query(self, text: str, k: int = 5,
              threshold: float = 0.0) -> list[tuple[str, float, dict]]: ...

    def backend_name(self) -> str: ...

    def health(self) -> str: ...


_WORD_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")

# Words too common in this enterprise's prose to carry topic signal. Kept short
# and explicit — an aggressive stoplist silently reshapes every score. IDF does
# most of this work; the list only removes what would otherwise dominate the
# token count before weighting.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those is are was were be been
being to of in on for with as at by from it its it's not no do does did done
you your we our i me my he she they them their there here what which who whom
when where why how all any both each few more most other some such only own
same so too very can will just should now would could may might must have has
had also into out up down over under about after before while because
""".split())


def normalise(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.lower()
    folded = _WORD_RE.sub(" ", folded)
    return _WS_RE.sub(" ", folded).strip()


def content_tokens(text: str) -> set[str]:
    """Distinctive word set: lowercased, punctuation-free, stopword-filtered."""
    return {w for w in normalise(text).split() if w not in _STOPWORDS and len(w) > 2}


def trigrams(text: str) -> set[str]:
    """Character trigrams. Retained for very short texts, where a handful of
    tokens gives token overlap nothing to work with."""
    norm = normalise(text)
    if len(norm) < 3:
        return {norm} if norm else set()
    return {norm[i:i + 3] for i in range(len(norm) - 2)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if intersection == 0:
        return 0.0
    return intersection / len(left | right)


class Vocabulary:
    """Inverse document frequency over a corpus, so rare words outweigh common ones.

    Built once per pass from whatever collection is being compared. An unseen
    word gets the maximum weight: a term this corpus has never used is the most
    distinctive thing a text can contain, and defaulting it low would silently
    discard the strongest signal available.
    """

    def __init__(self, documents: Iterable[str] | None = None):
        self.document_count = 0
        self.frequency: Counter[str] = Counter()
        if documents is not None:
            self.fit(documents)

    def fit(self, documents: Iterable[str]) -> "Vocabulary":
        for document in documents:
            self.document_count += 1
            for token in content_tokens(document):
                self.frequency[token] += 1
        return self

    def weight(self, token: str) -> float:
        if self.document_count <= 0:
            return 1.0
        seen = self.frequency.get(token, 0)
        return math.log((self.document_count + 1) / (seen + 1)) + 1.0

    def max_weight(self) -> float:
        """Weight of a token this corpus has never seen — the ceiling."""
        if self.document_count <= 0:
            return 1.0
        return math.log(self.document_count + 1) + 1.0

    def rarity(self, token: str) -> float:
        """`weight` normalised to (0, 1]. Corpus-size independent.

        Raw IDF mass cannot be compared against a fixed floor, because the
        weights themselves scale with corpus size — a threshold tuned on 800
        utterances rejects everything on a corpus of 5, which is exactly how a
        freshly-installed pipeline would report every memory as an inference and
        look like it was working. Normalising makes the floor mean the same
        thing at any corpus size.
        """
        ceiling = self.max_weight()
        return self.weight(token) / ceiling if ceiling else 1.0

    def mass(self, tokens: Iterable[str]) -> float:
        return sum(self.weight(token) for token in tokens)

    def rarity_mass(self, tokens: Iterable[str]) -> float:
        return sum(self.rarity(token) for token in tokens)

    def norm(self, tokens: Iterable[str]) -> float:
        return math.sqrt(sum(self.weight(token) ** 2 for token in tokens))

    def score(self, left: set[str], right: set[str],
              min_shared: int = 0) -> tuple[float, int, float]:
        """IDF cosine over binary term vectors: `(score, shared_count, rarity)`.

        Cosine, not the shared-over-lighter ratio the first version used. That
        ratio reaches 1.0 whenever the smaller text's vocabulary is fully
        contained in the larger one, which for a four-line instruction passage
        against a four-hundred-word concept is almost always — so every
        contradiction candidate scored exactly 1.0 and "ranked and capped"
        picked arbitrarily. Measured 2026-08-09; it is the same saturation the
        character-trigram version had, one level up.

        Cosine divides by both norms, so a short passage matching a long concept
        on a few rare words scores meaningfully below two texts that genuinely
        cover the same ground. It cannot reach 1.0 unless the token sets are
        equal, which is the property the ranking needs.
        """
        if not left or not right:
            return 0.0, 0, 0.0
        shared = left & right
        if len(shared) < min_shared or not shared:
            return 0.0, len(shared), 0.0
        numerator = sum(self.weight(token) ** 2 for token in shared)
        denominator = self.norm(left) * self.norm(right)
        score = numerator / denominator if denominator else 0.0
        return min(score, 1.0), len(shared), self.rarity_mass(shared)


_FLAT = Vocabulary()  # unfitted: every weight 1.0, i.e. plain token overlap


def similarity(a: str, b: str, vocabulary: Vocabulary | None = None) -> float:
    """Topic similarity in [0, 1]. Length-tolerant, IDF-weighted when fitted."""
    ta, tb = content_tokens(a), content_tokens(b)
    if len(ta) < 3 or len(tb) < 3:
        # Too few distinctive words to weigh; fall back to characters.
        return jaccard(trigrams(a), trigrams(b))
    score, _, _ = (vocabulary or _FLAT).score(ta, tb)
    return score


class LexicalIndex:
    """In-memory token index. Linear scan with a shared-token pre-filter.

    Sized for this job deliberately: ~160 concepts, ~700 instruction passages, a
    few thousand utterances. A linear scan over that is milliseconds, with no
    dependency, no model download and no separate store to keep in sync.
    """

    def __init__(self, vocabulary: Vocabulary | None = None,
                 min_shared_tokens: int = 3):
        self._keys: list[str] = []
        self._texts: list[str] = []
        self._tokens: list[set[str]] = []
        self._meta: list[dict] = []
        self.vocabulary = vocabulary
        self.min_shared_tokens = min_shared_tokens

    def __len__(self) -> int:
        return len(self._keys)

    def backend_name(self) -> str:
        fitted = self.vocabulary is not None and self.vocabulary.document_count > 0
        return f"lexical-idf-token/2{'' if fitted else '-unweighted'}"

    def health(self) -> str:
        return "ok" if self._keys else "degraded"

    def add(self, key: str, text: str, meta: dict | None = None) -> None:
        tokens = content_tokens(text)
        if not tokens:
            return
        self._keys.append(key)
        self._texts.append(text)
        self._tokens.append(tokens)
        self._meta.append(meta or {})

    def add_many(self, rows: Iterable[tuple[str, str, dict]]) -> None:
        for key, text, meta in rows:
            self.add(key, text, meta)

    def fit_vocabulary(self) -> "LexicalIndex":
        """Weight terms by how common they are across this index's own contents."""
        self.vocabulary = Vocabulary(self._texts)
        return self

    def query(self, text: str, k: int = 5, threshold: float = 0.0,
              exclude: Sequence[str] = (),
              max_score: float | None = None) -> list[tuple[str, float, dict]]:
        """Top-k entries scoring at or above `threshold`, best first.

        `max_score` drops near-identical matches. Used by the collision leg: an
        auto-memory card and the concept graduated *from* it score 1.0, and
        showing a reader fifteen copies of "this text equals this text" buries
        the collisions that need a ruling.
        """
        tokens = content_tokens(text)
        if not tokens:
            return []
        vocabulary = self.vocabulary or _FLAT
        excluded = set(exclude)
        scored: list[tuple[str, float, dict]] = []

        for idx, key in enumerate(self._keys):
            if key in excluded:
                continue
            other = self._tokens[idx]
            if len(tokens & other) < self.min_shared_tokens:
                continue
            score, _, _ = vocabulary.score(tokens, other,
                                           min_shared=self.min_shared_tokens)
            if score < threshold or score <= 0:
                continue
            if max_score is not None and score >= max_score:
                continue
            scored.append((key, score, self._meta[idx]))

        scored.sort(key=lambda row: row[1], reverse=True)
        return scored[:k]

    def text_for(self, key: str) -> str | None:
        try:
            return self._texts[self._keys.index(key)]
        except ValueError:
            return None


def cluster(texts: Sequence[tuple[str, str]], threshold: float,
            vocabulary: Vocabulary | None = None,
            min_shared_tokens: int = 4) -> list[list[str]]:
    """Single-link agglomerative clustering over (key, text) pairs.

    Returns clusters as lists of keys, largest first. Single-link is chosen for
    explainability rather than quality: it is the cheapest algorithm whose
    behaviour can be described to whoever reads a resulting candidate, and every
    candidate it produces is shown to a human before it becomes anything.

    `min_shared_tokens` is what keeps single-link from chaining. Without it, the
    trigram version merged 214 utterances into 4 components on the live corpus.
    """
    if not texts:
        return []

    vocabulary = vocabulary or Vocabulary(text for _, text in texts)
    entries = [(key, content_tokens(text)) for key, text in texts]
    parent = list(range(len(entries)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(entries)):
        _, ti = entries[i]
        if len(ti) < min_shared_tokens:
            continue
        for j in range(i + 1, len(entries)):
            _, tj = entries[j]
            if len(tj) < min_shared_tokens:
                continue
            if len(ti & tj) < min_shared_tokens:
                continue
            score, _, _ = vocabulary.score(ti, tj, min_shared=min_shared_tokens)
            if score >= threshold:
                union(i, j)

    buckets: dict[int, list[str]] = {}
    for idx, (key, _) in enumerate(entries):
        buckets.setdefault(find(idx), []).append(key)

    return sorted(buckets.values(), key=len, reverse=True)


def centroid_text(texts: Sequence[str],
                  vocabulary: Vocabulary | None = None) -> str:
    """The member closest to every other member — the cluster's representative.

    A medoid, not a mean: there is no vector to average, and a real utterance is
    a better thing to put in front of a person than a synthesised one.
    """
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    vocabulary = vocabulary or Vocabulary(texts)
    token_sets = [content_tokens(t) for t in texts]
    best_idx, best_score = 0, -math.inf
    for i, ti in enumerate(token_sets):
        total = sum(vocabulary.score(ti, tj)[0]
                    for j, tj in enumerate(token_sets) if i != j)
        if total > best_score:
            best_idx, best_score = i, total
    return texts[best_idx]


def anchor_score(memory_text: str, utterance: str,
                 vocabulary: Vocabulary | None = None,
                 min_utterance_tokens: int = 8,
                 min_shared_tokens: int = 10,
                 min_shared_rarity: float = 4.0) -> tuple[float, int, float]:
    """Does this utterance plausibly *say* what this memory claims?

    Returns `(score, shared_token_count, shared_rarity_mass)`. Three floors, each
    closing a failure observed on the live corpus:

    * `min_utterance_tokens` — a five-word aside cannot anchor a paragraph;
    * `min_shared_tokens` — separates a restatement (34 shared words on the
      commit-without-asking card) from a coincidence (5);
    * `min_shared_rarity` — the important one. Two long texts share a dozen
      middling words by accident; a real restatement shares *rare* ones. Without
      it, a Zgent-taxonomy concept anchored to Steve's commit-permissions
      message on twelve generic shared words. Expressed in normalised rarity so
      the floor means the same thing on a corpus of five utterances and a corpus
      of eight hundred.

    The floors are deliberately strict. A false "Steve stated this" is the
    expensive error — it lets an unverified inference pass unflagged, which is
    what this pipeline exists to catch. A false "COO inference" costs a glance,
    and the quote is displayed either way so the reader can overrule the label
    on sight.
    """
    vocabulary = vocabulary or _FLAT
    memory = content_tokens(memory_text)
    spoken = content_tokens(utterance)
    if len(spoken) < min_utterance_tokens or not memory:
        return 0.0, 0, 0.0
    shared = memory & spoken
    if len(shared) < min_shared_tokens:
        return 0.0, len(shared), 0.0
    rarity = vocabulary.rarity_mass(shared)
    if rarity < min_shared_rarity:
        return 0.0, len(shared), rarity
    spoken_mass = vocabulary.mass(spoken)
    union_mass = vocabulary.mass(memory | spoken)
    mass = vocabulary.mass(shared)
    score = max(mass / spoken_mass if spoken_mass else 0.0,
                mass / union_mass if union_mass else 0.0)
    return score, len(shared), rarity
