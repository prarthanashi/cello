"""L5/L6 — document ingestion and a small, replaceable keyword retriever (BM25-style).

Chunks always carry: scheme_id, url, source_title, page_or_section, last_verified_at.
Ingestion is review-gated: a document is only indexed if its scheme exists and its URL is one of
that scheme's official source URLs. Scanned PDFs with no text are reported, never indexed (E12).
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .catalogue import Catalogue, parse_iso_date

log = logging.getLogger("benefitbridge.retrieval")
MAX_CHUNK_CHARS = 900
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


# ---------------------------------------------------------------- ingestion
def _split(text: str) -> list[str]:
    parts, buf = [], ""
    for para in re.split(r"\n\s*\n", text.strip()):
        if buf and len(buf) + len(para) > MAX_CHUNK_CHARS:
            parts.append(buf.strip())
            buf = ""
        buf += para.strip() + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _parse_markdown(path: Path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError("missing front matter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    sections, current, buf = [], "Overview", []
    for line in m.group(2).splitlines():
        if line.startswith("## "):
            if "".join(buf).strip():
                sections.append((current, "\n".join(buf)))
            current, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((current, "\n".join(buf)))
    return meta, sections


def _check_meta(meta: dict, catalogue: Catalogue, name: str) -> str | None:
    scheme = catalogue.get(meta.get("scheme_id", ""))
    if scheme is None:
        return f"{name}: unknown scheme_id; document not indexed"
    if meta.get("url") not in scheme.official_source_urls:
        return f"{name}: url is not an official source URL of {scheme.scheme_id}; document not indexed"
    if not meta.get("title") or parse_iso_date(meta.get("verified")) is None:
        return f"{name}: needs title and ISO 'verified' date; document not indexed"
    return None


def _ingest_pdf(path: Path, catalogue: Catalogue):
    sidecar = path.with_suffix(path.suffix + ".json")
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], [f"{path.name}: missing or invalid metadata sidecar ({sidecar.name}); document not indexed"]
    err = _check_meta(meta, catalogue, path.name)
    if err:
        return [], [err]
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return [], [f"{path.name}: pypdf is not installed; PDF not indexed"]
    chunks = []
    try:
        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            for j, part in enumerate(_split(text) if text else []):
                chunks.append(Chunk(f"{meta['scheme_id']}:{path.stem}:p{i}:{j}", meta["scheme_id"], part,
                                    meta["title"], meta["url"], f"page {i}", meta["verified"]))
    except Exception as exc:  # corrupt PDFs must not crash startup
        return [], [f"{path.name}: could not be read ({type(exc).__name__}); document not indexed"]
    if not chunks:  # E12
        return [], [f"{path.name}: No readable text was found. Use a text-based PDF or review this document manually."]
    return chunks, []


def ingest_documents(directory: Path, catalogue: Catalogue) -> tuple[list[Chunk], list[str]]:
    chunks: list[Chunk] = []
    warnings: list[str] = []
    directory = Path(directory)
    if not directory.is_dir():
        return [], [f"documents directory not found: {directory.name}"]
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() in (".md", ".txt"):
            try:
                meta, sections = _parse_markdown(path)
            except (OSError, ValueError) as exc:
                warnings.append(f"{path.name}: {exc}; document not indexed")
                continue
            err = _check_meta(meta, catalogue, path.name)
            if err:
                warnings.append(err)
                continue
            for section, body in sections:
                for j, part in enumerate(_split(body)):
                    chunks.append(Chunk(f"{meta['scheme_id']}:{path.stem}:{section.lower().replace(' ', '-')}:{j}",
                                        meta["scheme_id"], part, meta["title"], meta["url"], section, meta["verified"]))
        elif path.suffix.lower() == ".pdf":
            c, w = _ingest_pdf(path, catalogue)
            chunks += c
            warnings += w
    for w in warnings:
        log.warning("ingestion_warning %s", w)
    return chunks, warnings
