"""Tests des endpoints API pour Noto WhatsApp AI Bot"""
import pytest
import json
from unittest.mock import patch, AsyncMock, Mock
from fastapi.testclient import TestClient

from app.api.main import app
from app.models.database import User, get_db

pytestmark = pytest.mark.api


def test_health_check_endpoint(api_client):
    """Test du endpoint GET /health"""
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["service"] == "Perplexity WhatsApp Bot"


def test_webhook_verification_valid_token(api_client):
    """Test de la vérification webhook avec un token valide"""
    with patch.dict('os.environ', {'WHATSAPP_VERIFY_TOKEN': 'test_verify_token'}):
        response = api_client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify_token",
                "hub.challenge": "challenge_string_123"
            }
        )
        assert response.status_code == 200
        assert response.text == '"challenge_string_123"'


def test_webhook_verification_invalid_token(api_client):
    """Test de la vérification webhook avec un token invalide"""
    with patch.dict('os.environ', {'WHATSAPP_VERIFY_TOKEN': 'correct_token'}):
        response = api_client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_string"
            }
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_message_processing(api_client, test_db_session):
    """Test du endpoint POST /webhook pour les messages WhatsApp entrants"""
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "+33612345678",
                                    "type": "text",
                                    "text": {"body": "Bonjour"},
                                    "timestamp": "1234567890"
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    with patch('app.api.main.orchestrator.process_message', new_callable=AsyncMock) as mock_process:
        response = api_client.post("/webhook", json=webhook_payload)

        # Should always return 200 OK immediately
        assert response.status_code == 200
        assert response.json() == {"status": "received"}


def test_webhook_audio_message_received(api_client):
    """Test du webhook avec un message audio"""
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "+33612345678",
                                    "type": "audio",
                                    "audio": {"id": "audio_id_123"},
                                    "timestamp": "1234567890"
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    with patch('app.api.main.orchestrator.process_message', new_callable=AsyncMock):
        response = api_client.post("/webhook", json=webhook_payload)
        assert response.status_code == 200


def test_webhook_status_update_ignored(api_client):
    """Test que les mises à jour de statut (accusés de lecture, etc.) sont ignorées"""
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": "msg_id_123",
                                    "status": "read"
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = api_client.post("/webhook", json=webhook_payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_test_message_endpoint(api_client, test_db_session, test_user):
    """Test du endpoint /test/message"""
    payload = {
        "phone_number": test_user.phone_number,
        "message": "test actualités"
    }

    with patch('app.api.main.orchestrator.process_message', new_callable=AsyncMock) as mock_process:
        mock_process.return_value = None

        response = api_client.post("/test/message", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["phone_number"] == test_user.phone_number


def test_test_services_health_endpoint(api_client):
    """Test du endpoint /test/services pour les health checks"""
    with patch('app.api.main.orchestrator.llm_service.health_check',
               new_callable=AsyncMock) as mock_llm_health, \
         patch('app.api.main.orchestrator.tts_service.health_check',
               new_callable=AsyncMock) as mock_tts_health:

        mock_llm_health.return_value = {"status": "healthy", "model": "llama3-8b-8192"}
        mock_tts_health.return_value = {"status": "healthy", "device": "mps"}

        response = api_client.get("/test/services")

        assert response.status_code == 200
        data = response.json()
        assert "llm" in data
        assert "tts" in data


@pytest.mark.asyncio
async def test_test_briefing_endpoint(api_client, test_db_session):
    """Test du endpoint /test/briefing"""
    payload = {
        "phone_number": "+33698765432",
        "topic": "actualités tech"
    }

    with patch('app.api.main.orchestrator.generate_daily_brief',
               new_callable=AsyncMock) as mock_brief:
        mock_brief.return_value = None

        response = api_client.post("/test/briefing", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generating"


def test_cors_headers_present(api_client):
    """Test que les headers CORS sont correctement configurés"""
    response = api_client.options(
        "/health",
        headers={"Origin": "http://localhost:3000"}
    )
    # CORS should allow the request
    assert response.status_code in [200, 204]


def test_invalid_webhook_payload(api_client):
    """Test du webhook avec un payload mal formé"""
    invalid_payload = {
        "invalid": "payload"
    }

    response = api_client.post("/webhook", json=invalid_payload)
    # Should still return 200 to avoid retries
    assert response.status_code == 200


def test_empty_webhook_payload(api_client):
    """Test du webhook avec un payload vide"""
    response = api_client.post("/webhook", json={})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_webhook_requests(api_client):
    """Test que plusieurs requêtes webhook sont gérées en concurrence"""
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "+33612345678",
                                    "type": "text",
                                    "text": {"body": f"Message {i}"},
                                    "timestamp": "1234567890"
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    with patch('app.api.main.orchestrator.process_message', new_callable=AsyncMock):
        # Send multiple requests
        responses = []
        for i in range(5):
            response = api_client.post("/webhook", json=webhook_payload)
            responses.append(response)

        # All should return 200 immediately
        for response in responses:
            assert response.status_code == 200
