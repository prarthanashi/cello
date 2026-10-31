import json
import tempfile
import unittest
from pathlib import Path

from app.config import PROJECT_ROOT
from app.retrieval import KeywordRetriever, ingest_documents
from app.catalogue import load_catalogue
from .helpers import catalogue_of, make_settings, raw_scheme


def real_retriever():
    s = make_settings()
    cat = load_catalogue(s.data_path, s.official_domain_suffixes)
    chunks, warnings = ingest_documents(s.documents_path, cat)
    return KeywordRetriever(chunks), chunks, warnings


class RetrievalTests(unittest.TestCase):
    def test_seed_documents_ingest_cleanly_with_metadata(self):
        _, chunks, warnings = real_retriever()
        self.assertEqual(warnings, [])
        for ch in chunks:
            self.assertTrue(ch.scheme_id and ch.url and ch.source_title and ch.last_verified_at and ch.page_or_section)

    def test_relevant_question_retrieves_scoped_chunks(self):
        r, _, _ = real_retriever()
        hits = r.search("Which documents are listed?", scheme_id="in-central-pmmy")
        self.assertTrue(hits)
        self.assertTrue(all(h.scheme_id == "in-central-pmmy" for h in hits))
        self.assertEqual(hits[0].page_or_section, "Documents")

    def test_irrelevant_question_returns_nothing(self):
        r, _, _ = real_retriever()
        self.assertEqual(r.search("Who won the cricket world cup?"), [])
        self.assertEqual(r.search("???"), [])

    def test_document_with_unofficial_url_is_not_indexed(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "bad.md").write_text("---\nscheme_id: test-central-scheme\ntitle: T\nurl: https://blog.example.com/x\nverified: 2026-10-31\n---\n## A\ntext", encoding="utf-8")
            Path(d, "nometa.md").write_text("no front matter", encoding="utf-8")
            Path(d, "unknown.md").write_text("---\nscheme_id: nope\ntitle: T\nurl: https://example.gov.in/scheme\nverified: 2026-10-31\n---\n## A\ntext", encoding="utf-8")
            chunks, warnings = ingest_documents(Path(d), catalogue_of(raw_scheme()))
        self.assertEqual(chunks, [])
        self.assertEqual(len(warnings), 3)

    def test_scanned_pdf_without_text_is_reported_not_indexed(self):  # E12
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest("pypdf not installed")
        with tempfile.TemporaryDirectory() as d:
            w = PdfWriter()
            w.add_blank_page(width=200, height=200)
            with open(Path(d, "scan.pdf"), "wb") as fh:
                w.write(fh)
            Path(d, "scan.pdf.json").write_text(json.dumps({"scheme_id": "test-central-scheme", "title": "Scan",
                                                            "url": "https://example.gov.in/scheme", "verified": "2026-10-31"}), encoding="utf-8")
            chunks, warnings = ingest_documents(Path(d), catalogue_of(raw_scheme()))
        self.assertEqual(chunks, [])
        self.assertIn("No readable text", warnings[0])


if __name__ == "__main__":
    unittest.main()
