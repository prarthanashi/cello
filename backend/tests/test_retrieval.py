import unittest

from app.retrieval import KeywordRetriever, catalogue_chunks
from .helpers import catalogue_of, raw_scheme


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = catalogue_of(raw_scheme(
            summary="Support for small businesses.",
            benefits=["A working capital loan is available."],
            eligibility_rules=[{
                "field": "business_stage", "operator": "in", "value": ["newly_operating"],
                "mandatory": True, "explanation": "New businesses may apply.",
                "source_excerpt": "New businesses may apply.",
            }],
            required_documents=[{
                "name": "Identity document", "requirement_type": "required", "notes": "Provide a valid identity document."
            }],
        ))
        self.chunks = catalogue_chunks(self.catalogue)
        self.retriever = KeywordRetriever(self.chunks)

    def test_chunks_use_persisted_scheme_fields_and_source_metadata(self):
        self.assertTrue(self.chunks)
        for chunk in self.chunks:
            self.assertEqual(chunk.scheme_id, "test-central-scheme")
            self.assertTrue(chunk.url and chunk.source_title and chunk.last_verified_at and chunk.page_or_section)
        self.assertTrue(any("New businesses may apply." in chunk.text for chunk in self.chunks))

    def test_relevant_question_retrieves_scoped_chunks(self):
        hits = self.retriever.search("Which documents are listed?", scheme_id="test-central-scheme")
        self.assertTrue(hits)
        self.assertTrue(all(hit.scheme_id == "test-central-scheme" for hit in hits))
        self.assertEqual(hits[0].page_or_section, "Documents")

    def test_irrelevant_question_returns_nothing(self):
        self.assertEqual(self.retriever.search("Who won the cricket world cup?"), [])
        self.assertEqual(self.retriever.search("???"), [])

    def test_scheme_without_official_source_is_not_indexed(self):
        catalogue = catalogue_of(raw_scheme(official_source_urls=[]))
        self.assertEqual(catalogue_chunks(catalogue), [])


if __name__ == "__main__":
    unittest.main()
