"""A small, replaceable keyword retriever (BM25-style) over Supabase scheme records."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Protocol

from .catalogue import Catalogue

MIN_SCORE = 0.35

STOPWORDS = set(
    "a an the is are was were be been am do does did can could should would will i me my we our you your "
    "what which who whom how when where why of to in on for and or if it its this that these those "
    "with from by at as about under into than then there any some please tell need want get".split()
)
SYNONYMS = {
    "eligible": ["eligibility", "who", "may", "apply"], "qualify": ["eligibility", "may", "apply"],
    "apply": ["application", "how"], "documents": ["document", "checklist"],
    "paperwork": ["document"], "amount": ["subsidy", "limit", "benefit"],
    "money": ["subsidy", "benefit"], "loan": ["credit", "loans"],
}


@dataclass
class Chunk:
    chunk_id: str
    scheme_id: str
    text: str
    source_title: str
    url: str
    page_or_section: str | None
    last_verified_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def _stem(tok: str) -> str:
    return tok[:-1] if len(tok) > 4 and tok.endswith("s") else tok


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9₹]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


def _expand(question: str) -> list[str]:
    toks = tokenize(question)
    extra = []
    for raw in re.findall(r"[a-z]+", question.lower()):
        extra += SYNONYMS.get(raw, [])
    return toks + [_stem(e) for e in extra]


class Retriever(Protocol):  # keep the retrieval interface replaceable (e.g. vector store)
    def search(self, question: str, scheme_id: str | None = None, top_k: int = 4) -> list[Chunk]: ...


class KeywordRetriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._tok = [tokenize(f"{ch.page_or_section or ''} {ch.page_or_section or ''} {ch.text}") for ch in chunks]
        n = max(len(chunks), 1)
        df: Counter = Counter()
        for toks in self._tok:
            df.update(set(toks))
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._avg = (sum(len(t) for t in self._tok) / n) or 1.0

    def search(self, question: str, scheme_id: str | None = None, top_k: int = 4) -> list[Chunk]:
        q = _expand(question)
        if not q:
            return []
        scored = []
        for ch, toks in zip(self.chunks, self._tok):
            if scheme_id and ch.scheme_id != scheme_id:
                continue
            tf = Counter(toks)
            score = 0.0
            matched = 0
            for t in set(q):
                if tf[t]:
                    matched += 1
                    score += self._idf.get(t, 0) * (tf[t] * 2.2) / (tf[t] + 1.2 * (0.25 + 0.75 * len(toks) / self._avg))
            if matched and score >= MIN_SCORE:
                scored.append((score, ch))
        scored.sort(key=lambda x: -x[0])
        return [ch for _, ch in scored[:top_k]]


def catalogue_chunks(catalogue: Catalogue) -> list[Chunk]:
    """Build assistant context from persisted scheme fields and grounded rule excerpts."""
    chunks: list[Chunk] = []
    for scheme in catalogue.all():
        if not scheme.official_source_urls:
            continue
        sections = [
            ("Overview", [scheme.summary]),
            ("Benefits", scheme.benefits),
            ("Eligibility", [
                text
                for rule in scheme.eligibility_rules
                for text in (rule.get("explanation", ""), rule.get("source_excerpt", ""))
            ]),
            ("Documents", [
                text
                for document in scheme.required_documents
                for text in (document.get("name", ""), document.get("notes", ""))
            ]),
            ("Application", scheme.application_steps),
            ("Exclusions", scheme.exclusions),
        ]
        for url_index, url in enumerate(scheme.official_source_urls):
            for section, values in sections:
                text = "\n".join(value.strip() for value in values if isinstance(value, str) and value.strip())
                if text:
                    chunks.append(Chunk(
                        f"{scheme.scheme_id}:source-{url_index}:{section.lower()}",
                        scheme.scheme_id,
                        text,
                        scheme.source_title or scheme.name,
                        url,
                        section,
                        scheme.last_verified_at,
                    ))
    return chunks
