"""Tests d'intégration pour Noto WhatsApp AI Bot"""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime

from app.services.orchestrator import MessageOrchestrator
from app.models.database import User, Preference, Conversation

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_onboarding_flow_complete(test_db_session, mock_whatsapp_service,
                                       mock_llm_service, mock_perplexica_service,
                                       mock_tts_service):
    """Test du flux d'onboarding complet de l'accueil à la finalisation"""
    orchestrator = MessageOrchestrator()
    orchestrator.whatsapp_service = mock_whatsapp_service
    orchestrator.llm_service = mock_llm_service
    orchestrator.perplexica_service = mock_perplexica_service
    orchestrator.tts_service = mock_tts_service

    phone_number = "+33698765432"

    # Step 1: Initial welcome
    await orchestrator.process_message(test_db_session, phone_number, "Bonjour", "text")

    user = test_db_session.query(User).filter(User.phone_number == phone_number).first()
    assert user is not None
    assert user.onboarding_state == "keywords"

    # Step 2: Provide keywords
    await orchestrator.process_message(test_db_session, phone_number,
                                      "politique, technologie, environnement", "text")

    test_db_session.refresh(user)
    assert user.onboarding_state == "schedule"

    # Step 3: Provide schedule
    await orchestrator.process_message(test_db_session, phone_number, "08:00", "text")

    test_db_session.refresh(user)
    assert user.onboarding_state == "voice"

    # Step 4: Skip voice setup
    await orchestrator.process_message(test_db_session, phone_number, "ignorer", "text")

    test_db_session.refresh(user)
    assert user.is_onboarded is True
    assert user.onboarding_state == "completed"

    # Verify preferences were created
    preference = test_db_session.query(Preference).filter(
        Preference.user_id == user.id
    ).first()
    assert preference is not None
    assert "politique" in preference.keywords


@pytest.mark.asyncio
async def test_search_query_pipeline_with_perplexica(test_db_session,
                                                     test_user_with_preferences,
                                                     mock_orchestrator):
    """Test du pipeline de recherche complet: query -> Perplexica -> LLM -> TTS -> WhatsApp"""
    # Mock Perplexica response with sources
    mock_orchestrator.perplexica_service.search_multi_interests.return_value = {
        "success": True,
        "interests_covered": ["politique", "technologie"],
        "sources": [
            {
                "title": "Nouvelle loi sur l'IA",
                "url": "https://example.com/ai-law",
                "content": "Le parlement vote une nouvelle réglementation...",
                "quality_score": 9
            }
        ]
    }

    mock_orchestrator.perplexica_service.format_for_whatsapp.return_value = {
        "summary": "Bonjour Test User ! Voici vos actualités du jour...",
        "sources": [
            {"title": "Nouvelle loi sur l'IA", "url": "https://example.com/ai-law"}
        ]
    }

    mock_orchestrator.tts_service.text_to_speech.return_value = "cache/audio/test.ogg"

    # Process search query
    await mock_orchestrator.process_message(
        test_db_session,
        test_user_with_preferences.phone_number,
        "actualités du jour",
        "text"
    )

    # Verify Perplexica was called with user interests
    mock_orchestrator.perplexica_service.search_multi_interests.assert_called_once()
    call_kwargs = mock_orchestrator.perplexica_service.search_multi_interests.call_args[1]
    assert "politique" in call_kwargs["interests"]

    # Verify audio was generated
    mock_orchestrator.tts_service.text_to_speech.assert_called_once()

    # Verify messages were sent
    assert mock_orchestrator.whatsapp_service.send_audio_message.call_count >= 1
    assert mock_orchestrator.whatsapp_service.send_text_message.call_count >= 1

    # Verify conversation was logged
    conversation = test_db_session.query(Conversation).filter(
        Conversation.user_id == test_user_with_preferences.id
    ).first()
    assert conversation is not None
    assert conversation.response_audio_url is not None


@pytest.mark.asyncio
async def test_fallback_handling_on_perplexica_failure(test_db_session,
                                                       test_user_with_preferences,
                                                       mock_orchestrator):
    """Test du comportement de fallback en cas d'échec de Perplexica"""
    # Simulate Perplexica failure
    mock_orchestrator.perplexica_service.search_multi_interests.return_value = {
        "success": False,
        "interests_covered": []
    }

    await mock_orchestrator.process_message(
        test_db_session,
        test_user_with_preferences.phone_number,
        "actualités",
        "text"
    )

    # Verify error message was sent
    mock_orchestrator.whatsapp_service.send_text_message.assert_called()
    call_args = mock_orchestrator.whatsapp_service.send_text_message.call_args[0]
    assert "Aucune actualité trouvée" in call_args[1]


@pytest.mark.asyncio
async def test_command_handling(test_db_session, test_user, mock_orchestrator):
    """Test du parsing et routage des commandes (/help, /start, etc.)"""
    # Test /help command
    await mock_orchestrator.process_message(
        test_db_session,
        test_user.phone_number,
        "/help",
        "text"
    )

    mock_orchestrator.whatsapp_service.send_text_message.assert_called()
    call_args = mock_orchestrator.whatsapp_service.send_text_message.call_args[0]
    assert "Commandes disponibles" in call_args[1] or "aide" in call_args[1].lower()


@pytest.mark.asyncio
async def test_conversation_logging_with_all_data(test_db_session,
                                                  test_user_with_preferences,
                                                  mock_orchestrator):
    """Test que toutes les données de conversation sont correctement loguées"""
    mock_orchestrator.perplexica_service.search_multi_interests.return_value = {
        "success": True,
        "interests_covered": ["sport"],
        "sources": [{"title": "Match PSG", "url": "https://example.com"}]
    }

    mock_orchestrator.perplexica_service.format_for_whatsapp.return_value = {
        "summary": "Le PSG gagne 3-0",
        "sources": [{"title": "Match PSG", "url": "https://example.com"}]
    }

    mock_orchestrator.tts_service.text_to_speech.return_value = "cache/audio/psg.ogg"

    query = "résultats PSG"
    await mock_orchestrator.process_message(
        test_db_session,
        test_user_with_preferences.phone_number,
        query,
        "text"
    )

    # Verify conversation record
    conversation = test_db_session.query(Conversation).filter(
        Conversation.user_id == test_user_with_preferences.id
    ).first()

    assert conversation is not None
    assert conversation.query == query
    assert conversation.response_text is not None
    assert conversation.response_audio_url == "cache/audio/psg.ogg"
    assert conversation.processing_time is not None
    assert conversation.created_at is not None


@pytest.mark.asyncio
async def test_user_preferences_update(test_db_session, test_user_with_preferences):
    """Test que les préférences utilisateur peuvent être mises à jour"""
    # Get current preferences
    preference = test_db_session.query(Preference).filter(
        Preference.user_id == test_user_with_preferences.id
    ).first()

    assert preference is not None

    # Update preferences
    preference.keywords = '["économie", "santé"]'
    preference.daily_schedule = "09:00"
    test_db_session.commit()

    # Verify update
    test_db_session.refresh(preference)
    assert "économie" in preference.keywords
    assert preference.daily_schedule == "09:00"


@pytest.mark.asyncio
async def test_error_handling_and_recovery(test_db_session,
                                          test_user_with_preferences,
                                          mock_orchestrator):
    """Test que les erreurs sont capturées et que des messages de fallback appropriés sont envoyés"""
    # Simulate exception in Perplexica
    mock_orchestrator.perplexica_service.search_multi_interests.side_effect = Exception(
        "API timeout"
    )

    # Should not crash, should send error message
    await mock_orchestrator.process_message(
        test_db_session,
        test_user_with_preferences.phone_number,
        "actualités",
        "text"
    )

    # Verify error message was sent
    mock_orchestrator.whatsapp_service.send_text_message.assert_called()
    call_args = mock_orchestrator.whatsapp_service.send_text_message.call_args[0]
    assert "Erreur" in call_args[1] or "erreur" in call_args[1]
