"""Unit tests for KeyFactsExtractor - validates intelligent content extraction"""
import pytest
from unittest.mock import patch, MagicMock

from app.utils.key_facts_extractor import KeyFactsExtractor


class TestKeyFactsExtractor:
    """Test suite for the KeyFactsExtractor intelligent content extraction.

    These tests validate the core AI logic for extracting key facts from
    long-form content using NER, factual pattern matching, and importance scoring.
    """

    @pytest.fixture
    def extractor(self):
        """Create a KeyFactsExtractor instance for testing."""
        return KeyFactsExtractor()

    @pytest.fixture
    def sample_news_content(self):
        """Sample news article with high-importance and low-importance sentences."""
        return """
        Le gouvernement annonce une hausse historique de 12% des investissements dans l'IA.
        Cette mesure fait suite à plusieurs mois de négociations intenses entre ministères.
        Selon l'INSEE, cette décision pourrait créer 50 000 emplois d'ici 2025.
        Les experts saluent cette initiative sans précédent dans le secteur tech.
        La météo reste clémente en ce début de semaine.
        Les marchés financiers ont réagi positivement avec une hausse de 3.5% du CAC 40.
        Cette information a été relayée par plusieurs médias nationaux.
        Un porte-parole a confirmé ces informations lors d'une conférence de presse.
        """

    def test_extract_key_facts_preserves_high_importance_sentences(
        self, extractor, sample_news_content
    ):
        """Test that high-importance sentences are prioritized in extraction.

        High-importance criteria:
        - Contains percentages (12%, 3.5%)
        - Contains named entities (gouvernement, INSEE)
        - Contains importance keywords (annonce, historique, selon)
        - Contains monetary/numerical data (50 000 emplois)
        """
        # Extract with tight character limit to force selection
        extracted = extractor.extract_key_facts(
            content=sample_news_content,
            interest_category="économie",
            max_chars=200
        )

        # Verify high-importance content is preserved
        assert "12%" in extracted, "Percentage should be preserved (high importance)"
        assert "50 000 emplois" in extracted or "emplois" in extracted, "Job numbers should be preserved"
        assert "gouvernement" in extracted or "INSEE" in extracted, "Key entities should be preserved"

        # Verify low-importance content is filtered out
        assert "météo" not in extracted, "Low-importance weather sentence should be filtered"
        assert len(extracted) <= 200, "Should respect character limit"

    def test_extract_key_facts_handles_short_content(self, extractor):
        """Test that content shorter than max_chars is returned unchanged."""
        short_content = "Le CAC 40 progresse de 2%."

        extracted = extractor.extract_key_facts(
            content=short_content,
            max_chars=500
        )

        assert extracted == short_content, "Short content should be returned as-is"

    def test_extract_key_facts_handles_empty_content(self, extractor):
        """Test graceful handling of empty or None content."""
        assert extractor.extract_key_facts(content="", max_chars=100) == ""
        assert extractor.extract_key_facts(content=None, max_chars=100) in [None, ""]

    def test_sentence_importance_scoring_with_entities(self, extractor):
        """Test that sentences with named entities receive higher scores."""
        sentence_with_entity = "Emmanuel Macron annonce une réforme majeure."
        sentence_without_entity = "Une réforme majeure est annoncée."

        # Mock SpaCy NER to return entities for first sentence only
        with patch('app.utils.key_facts_extractor.nlp') as mock_nlp:
            # Configure mock for sentence with entity
            mock_doc_with_entity = MagicMock()
            mock_entity = MagicMock()
            mock_entity.text = "Emmanuel Macron"
            mock_entity.label_ = "PERSON"
            mock_doc_with_entity.ents = [mock_entity]

            mock_nlp.return_value = mock_doc_with_entity

            score_with_entity = extractor._calculate_sentence_importance(
                sentence_with_entity,
                interest_category="politique"
            )

            # Configure mock for sentence without entity
            mock_doc_without_entity = MagicMock()
            mock_doc_without_entity.ents = []
            mock_nlp.return_value = mock_doc_without_entity

            score_without_entity = extractor._calculate_sentence_importance(
                sentence_without_entity,
                interest_category="politique"
            )

            # Sentence with named entity should score higher
            assert score_with_entity > score_without_entity, \
                "Sentences with PERSON entities should score higher"

    def test_factual_pattern_detection(self, extractor):
        """Test that factual patterns (%, €, dates) boost sentence scores."""
        sentence_with_facts = "L'inflation atteint 5.2% et le budget s'élève à 50 milliards d'euros."
        sentence_generic = "L'inflation est en hausse et le budget est élevé."

        score_with_facts = extractor._calculate_sentence_importance(
            sentence_with_facts,
            interest_category="économie"
        )

        score_generic = extractor._calculate_sentence_importance(
            sentence_generic,
            interest_category="économie"
        )

        assert score_with_facts > score_generic, \
            "Sentences with factual patterns (percentages, monetary values) should score higher"

    def test_category_specific_keyword_boosting(self, extractor):
        """Test that category-specific keywords boost relevance scores."""
        tech_sentence = "L'intelligence artificielle révolutionne le machine learning."
        generic_sentence = "Les nouvelles technologies évoluent rapidement."

        # Score with tech category should be higher for AI keywords
        score_tech_category = extractor._calculate_sentence_importance(
            tech_sentence,
            interest_category="technologie"
        )

        score_no_category = extractor._calculate_sentence_importance(
            tech_sentence,
            interest_category=None
        )

        assert score_tech_category >= score_no_category, \
            "Category-specific keywords should boost scores when category matches"

    def test_extract_key_facts_maintains_coherence(self, extractor, sample_news_content):
        """Test that extracted content maintains logical flow and proper punctuation."""
        extracted = extractor.extract_key_facts(
            content=sample_news_content,
            max_chars=300
        )

        # Verify proper sentence structure
        assert extracted.endswith(('.', '!', '?', '...')), \
            "Extracted content should end with proper punctuation"

        # Verify no orphaned fragments
        assert not extracted.endswith(','), \
            "Should not end with comma (indicates incomplete sentence)"

    def test_noise_sentence_filtering(self, extractor):
        """Test that noise sentences (navigation, ads) are filtered out."""
        content_with_noise = """
        Lire aussi: Nos autres articles.
        Le gouvernement annonce une réforme importante.
        Abonnez-vous à notre newsletter.
        Cette réforme impacte 5 millions de personnes.
        Plus d'informations sur notre site.
        """

        extracted = extractor.extract_key_facts(content_with_noise, max_chars=200)

        # Verify noise is filtered
        assert "Lire aussi" not in extracted, "Navigation text should be filtered"
        assert "Abonnez-vous" not in extracted, "Call-to-action should be filtered"
        assert "Plus d'informations" not in extracted, "Navigation links should be filtered"

        # Verify important content is kept
        assert "réforme" in extracted, "Important content should be preserved"

    @pytest.mark.parametrize("max_chars,expected_length_range", [
        (100, (50, 100)),
        (300, (200, 300)),
        (500, (400, 500)),
    ])
    def test_extract_key_facts_respects_character_limits(
        self, extractor, sample_news_content, max_chars, expected_length_range
    ):
        """Test that extraction respects various character limits."""
        extracted = extractor.extract_key_facts(
            content=sample_news_content,
            max_chars=max_chars
        )

        assert len(extracted) <= max_chars, \
            f"Extracted content should not exceed {max_chars} characters"

        # Should use most of available space (not waste too much)
        min_expected, max_expected = expected_length_range
        assert min_expected <= len(extracted) <= max_expected, \
            f"Should efficiently use character budget ({min_expected}-{max_expected} chars)"

    def test_analyze_content_distribution(self, extractor, sample_news_content):
        """Test the content analysis utility method."""
        analysis = extractor.analyze_content_distribution(
            content=sample_news_content,
            interest_category="économie"
        )

        # Verify analysis structure
        assert "total_sentences" in analysis
        assert "total_chars" in analysis
        assert "factual_sentences" in analysis
        assert "high_importance_sentences" in analysis
        assert "entities_found" in analysis

        # Verify reasonable values
        assert analysis["total_sentences"] > 0, "Should detect sentences"
        assert analysis["total_chars"] == len(sample_news_content)
        assert isinstance(analysis["entities_found"], dict)


# Integration test with real SpaCy model (if available)
@pytest.mark.integration
@pytest.mark.skipif(
    not pytest.importorskip("spacy", minversion="3.0"),
    reason="SpaCy not available for integration test"
)
class TestKeyFactsExtractorIntegration:
    """Integration tests with real SpaCy NER model."""

    @pytest.fixture
    def extractor_with_real_ner(self):
        """Create extractor with real SpaCy model loaded."""
        return KeyFactsExtractor()

    def test_real_ner_entity_extraction(self, extractor_with_real_ner):
        """Test NER with actual SpaCy model (integration test)."""
        content = """
        Emmanuel Macron et Bruno Le Maire ont annoncé un plan de relance.
        Microsoft et Google investissent massivement en France.
        L'INSEE confirme une croissance de 2.5% à Paris.
        """

        extracted = extractor_with_real_ner.extract_key_facts(
            content=content,
            interest_category="économie",
            max_chars=150
        )

        # With real NER, should prioritize sentences with prominent entities
        # (exact assertions depend on model, so just verify reasonable output)
        assert len(extracted) > 0
        assert len(extracted) <= 150
        # Should likely keep high-entity sentences
        assert any(name in extracted for name in ["Macron", "Microsoft", "Google", "INSEE"])
