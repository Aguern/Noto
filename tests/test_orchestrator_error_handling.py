"""Critical error handling tests for MessageOrchestrator"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import json

from app.services.orchestrator import MessageOrchestrator
from app.models.database import User, Preference

pytestmark = pytest.mark.integration


class TestOrchestratorErrorHandling:
    """Test suite for MessageOrchestrator error handling and resilience.

    These tests validate that the orchestrator gracefully handles various
    failure scenarios without crashing and provides appropriate user feedback.
    Critical for production reliability.
    """

    @pytest.fixture
    def orchestrator_with_mocks(self):
        """Create orchestrator with all services mocked."""
        orchestrator = MessageOrchestrator()

        # Mock all external services
        orchestrator.whatsapp_service = AsyncMock()
        orchestrator.perplexica_service = AsyncMock()
        orchestrator.llm_service = AsyncMock()
        orchestrator.tts_service = AsyncMock()
        orchestrator.news_collector = AsyncMock()
        orchestrator.news_summarizer = AsyncMock()

        return orchestrator

    @pytest.fixture
    def test_user_obj(self, test_db_session):
        """Create a test user object with preferences."""
        user = User(
            id=1,
            phone_number="+33612345678",
            name="Test User",
            language="fr",
            timezone="Europe/Paris",
            is_onboarded=True,
            onboarding_state="completed",
            onboarding_data=json.dumps({"keywords": ["tech", "économie"]})
        )
        test_db_session.add(user)

        preference = Preference(
            user_id=user.id,
            max_results=5,
            summary_style="concise",
            keywords=json.dumps(["tech", "économie"])
        )
        test_db_session.add(preference)
        test_db_session.commit()
        test_db_session.refresh(user)

        return user

    @pytest.mark.asyncio
    async def test_perplexica_api_timeout_handled_gracefully(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test that Perplexica API timeouts result in user-friendly error message.

        Critical: API timeouts should not crash the bot or leave users hanging.
        """
        # Simulate Perplexica timeout
        orchestrator_with_mocks.perplexica_service.search_multi_interests.side_effect = \
            asyncio.TimeoutError("API request timed out after 300s")

        # Process message
        await orchestrator_with_mocks._process_search_query(
            db=test_db_session,
            user=test_user_obj,
            query="actualités tech",
            start_time=datetime.utcnow()
        )

        # Verify error message was sent to user
        orchestrator_with_mocks.whatsapp_service.send_text_message.assert_called()
        call_args = orchestrator_with_mocks.whatsapp_service.send_text_message.call_args[0]
        error_message = call_args[1]

        assert "Erreur" in error_message or "erreur" in error_message, \
            "Should send error message to user"
        assert test_user_obj.phone_number in call_args, \
            "Should send to correct user"

    @pytest.mark.asyncio
    async def test_perplexica_returns_empty_results(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test handling when Perplexica finds no results for user query.

        Should inform user that no news was found, not crash or hang.
        """
        # Simulate empty Perplexica response
        orchestrator_with_mocks.perplexica_service.search_multi_interests.return_value = {
            "success": False,
            "interests_covered": [],
            "sources": []
        }

        await orchestrator_with_mocks._process_search_query(
            db=test_db_session,
            user=test_user_obj,
            query="actualités crypto quantique",
            start_time=datetime.utcnow()
        )

        # Verify appropriate "no results" message
        orchestrator_with_mocks.whatsapp_service.send_text_message.assert_called()
        call_args = orchestrator_with_mocks.whatsapp_service.send_text_message.call_args[0]
        message = call_args[1]

        assert "Aucune actualité trouvée" in message or "aucune" in message.lower(), \
            "Should inform user no results were found"

    @pytest.mark.asyncio
    async def test_llm_json_parsing_failure_handled(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test handling of malformed JSON responses from LLM.

        Critical: LLMs sometimes return invalid JSON. Must handle gracefully.
        """
        # Perplexica returns valid data
        orchestrator_with_mocks.perplexica_service.search_multi_interests.return_value = {
            "success": True,
            "interests_covered": ["tech"],
            "sources": [
                {"title": "AI News", "url": "https://example.com", "content": "..."}
            ]
        }

        # But format_for_whatsapp returns malformed data
        orchestrator_with_mocks.perplexica_service.format_for_whatsapp.side_effect = \
            json.JSONDecodeError("Expecting value", "doc", 0)

        await orchestrator_with_mocks._process_search_query(
            db=test_db_session,
            user=test_user_obj,
            query="actualités AI",
            start_time=datetime.utcnow()
        )

        # Should send error message, not crash
        orchestrator_with_mocks.whatsapp_service.send_text_message.assert_called()
        call_args = orchestrator_with_mocks.whatsapp_service.send_text_message.call_args[0]
        assert "Erreur" in call_args[1] or "erreur" in call_args[1]

    @pytest.mark.asyncio
    async def test_tts_service_failure_falls_back_to_text(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test that TTS failures fall back to text-only responses.

        Users should still receive information even if audio generation fails.
        """
        # Perplexica and formatting succeed
        orchestrator_with_mocks.perplexica_service.search_multi_interests.return_value = {
            "success": True,
            "interests_covered": ["tech"],
            "sources": [{"title": "News", "url": "https://example.com"}]
        }

        orchestrator_with_mocks.perplexica_service.format_for_whatsapp.return_value = {
            "summary": "Voici vos actualités tech du jour.",
            "sources": [{"title": "News", "url": "https://example.com"}]
        }

        # But TTS fails
        orchestrator_with_mocks.tts_service.text_to_speech.return_value = None

        await orchestrator_with_mocks._process_search_query(
            db=test_db_session,
            user=test_user_obj,
            query="actualités tech",
            start_time=datetime.utcnow()
        )

        # Verify fallback to text message
        orchestrator_with_mocks.whatsapp_service.send_text_message.assert_called()
        call_args = orchestrator_with_mocks.whatsapp_service.send_text_message.call_args[0]
        assert "actualités tech" in call_args[1] or "tech" in call_args[1], \
            "Should send text summary as fallback"

        # Verify audio was NOT sent (since TTS failed)
        orchestrator_with_mocks.whatsapp_service.send_audio_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_database_connection_failure_during_logging(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test that database failures during conversation logging don't crash pipeline.

        The response should be sent to user even if logging fails.
        """
        # Mock successful search and formatting
        orchestrator_with_mocks.perplexica_service.search_multi_interests.return_value = {
            "success": True,
            "interests_covered": ["sport"],
            "sources": [{"title": "Match", "url": "https://example.com"}]
        }

        orchestrator_with_mocks.perplexica_service.format_for_whatsapp.return_value = {
            "summary": "Le PSG gagne 3-0",
            "sources": [{"title": "Match", "url": "https://example.com"}]
        }

        orchestrator_with_mocks.tts_service.text_to_speech.return_value = "audio/test.ogg"

        # Simulate database failure during conversation logging
        with patch.object(test_db_session, 'add', side_effect=Exception("DB connection lost")):
            # Should not raise exception
            await orchestrator_with_mocks._process_search_query(
                db=test_db_session,
                user=test_user_obj,
                query="résultats PSG",
                start_time=datetime.utcnow()
            )

        # Verify message was still sent despite logging failure
        assert orchestrator_with_mocks.whatsapp_service.send_audio_message.call_count >= 1, \
            "Should send response even if logging fails"

    @pytest.mark.asyncio
    async def test_whatsapp_api_send_failure_is_logged(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test that WhatsApp API send failures are properly logged.

        Cannot recover from send failures, but should log for monitoring.
        """
        # Mock successful pipeline
        orchestrator_with_mocks.perplexica_service.search_multi_interests.return_value = {
            "success": True,
            "interests_covered": ["économie"],
            "sources": []
        }

        orchestrator_with_mocks.perplexica_service.format_for_whatsapp.return_value = {
            "summary": "Actualités économie",
            "sources": []
        }

        orchestrator_with_mocks.tts_service.text_to_speech.return_value = "audio/test.ogg"

        # WhatsApp API fails to send
        orchestrator_with_mocks.whatsapp_service.send_audio_message.side_effect = \
            Exception("WhatsApp API error: 403 Forbidden")

        # Should not crash
        with patch('app.services.orchestrator.logger') as mock_logger:
            await orchestrator_with_mocks._process_search_query(
                db=test_db_session,
                user=test_user_obj,
                query="actualités économie",
                start_time=datetime.utcnow()
            )

            # Verify error was logged
            assert mock_logger.error.called, "WhatsApp send failures should be logged"

    @pytest.mark.asyncio
    async def test_news_collector_rate_limit_handled(
        self, orchestrator_with_mocks, test_db_session, test_user_obj
    ):
        """Test handling of API rate limit errors from news collection.

        Should inform user to try again later, not expose technical details.
        """
        # Simulate rate limit error
        orchestrator_with_mocks.news_collector.collect_news.side_effect = \
            Exception("Rate limit exceeded: 429 Too Many Requests")

        await orchestrator_with_mocks.generate_daily_brief(
            db=test_db_session,
            user=test_user_obj,
            topic="tech"
        )

        # Verify user-friendly error message
        orchestrator_with_mocks.whatsapp_service.send_text_message.assert_called()
        call_args = orchestrator_with_mocks.whatsapp_service.send_text_message.call_args[0]
        message = call_args[1]

        assert "Erreur" in message or "Réessayez" in message, \
            "Should ask user to retry, not expose technical error"
        assert "429" not in message and "Rate limit" not in message, \
            "Should not expose technical details to end user"

    @pytest.mark.asyncio
    async def test_concurrent_message_processing_isolation(
        self, orchestrator_with_mocks, test_db_session
    ):
        """Test that errors in one user's message don't affect others.

        Critical for multi-user stability in production.
        """
        # Create two users
        user1 = User(
            phone_number="+33611111111",
            name="User 1",
            language="fr",
            is_onboarded=True,
            onboarding_state="completed",
            onboarding_data=json.dumps({"keywords": ["tech"]})
        )
        user2 = User(
            phone_number="+33622222222",
            name="User 2",
            language="fr",
            is_onboarded=True,
            onboarding_state="completed",
            onboarding_data=json.dumps({"keywords": ["sport"]})
        )
        test_db_session.add_all([user1, user2])
        test_db_session.commit()

        # User 1's request will fail
        orchestrator_with_mocks.perplexica_service.search_multi_interests.side_effect = [
            Exception("API error for user 1"),  # First call fails
            {  # Second call succeeds
                "success": True,
                "interests_covered": ["sport"],
                "sources": []
            }
        ]

        orchestrator_with_mocks.perplexica_service.format_for_whatsapp.return_value = {
            "summary": "Actualités sport",
            "sources": []
        }

        # Process both messages
        await orchestrator_with_mocks._process_search_query(
            db=test_db_session,
            user=user1,
            query="actualités tech",
            start_time=datetime.utcnow()
        )

        await orchestrator_with_mocks._process_search_query(
            db=test_db_session,
            user=user2,
            query="actualités sport",
            start_time=datetime.utcnow()
        )

        # Verify user 1 got error message
        calls = orchestrator_with_mocks.whatsapp_service.send_text_message.call_args_list
        user1_calls = [c for c in calls if user1.phone_number in c[0]]
        assert len(user1_calls) > 0, "User 1 should receive error message"

        # Verify user 2 got successful response (not affected by user 1's error)
        user2_calls = [c for c in calls if user2.phone_number in c[0]]
        assert len(user2_calls) > 0, "User 2 should receive successful response"

        # User 2's message should not contain error
        user2_message = user2_calls[0][0][1]
        assert "Erreur" not in user2_message, \
            "User 2 should not be affected by user 1's error"


# Additional import for asyncio timeout test
import asyncio


@pytest.fixture(autouse=True)
def import_asyncio():
    """Ensure asyncio is available for timeout tests."""
    return asyncio
