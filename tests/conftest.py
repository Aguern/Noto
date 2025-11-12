"""Configuration pytest et fixtures pour les tests"""
import os
import sys
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.database import Base, User, Preference, VoiceProfile
from app.api.main import app

# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_noto.db"

@pytest.fixture(scope="function")
def test_db_engine():
    """Create a test database engine"""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    # Clean up test database file
    if os.path.exists("test_noto.db"):
        os.remove("test_noto.db")

@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Create a test database session"""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture(scope="function")
def test_user(test_db_session):
    """Create a test user"""
    user = User(
        phone_number="+33612345678",
        name="Test User",
        language="fr",
        timezone="Europe/Paris",
        is_active=True,
        is_onboarded=True,
        onboarding_state="completed"
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user

@pytest.fixture(scope="function")
def test_user_with_preferences(test_db_session, test_user):
    """Create a test user with preferences"""
    preference = Preference(
        user_id=test_user.id,
        keywords='["politique", "technologie", "sport"]',
        daily_schedule="08:00",
        channels='["whatsapp"]',
        max_results=5,
        summary_style="concise"
    )
    test_db_session.add(preference)
    test_db_session.commit()
    return test_user

@pytest.fixture
def mock_whatsapp_service():
    """Mock WhatsApp service"""
    mock = AsyncMock()
    mock.send_text_message = AsyncMock(return_value=True)
    mock.send_audio_message = AsyncMock(return_value=True)
    mock.verify_webhook = Mock(return_value=True)
    return mock

@pytest.fixture
def mock_llm_service():
    """Mock LLM service"""
    mock = AsyncMock()
    mock.summarize_for_whatsapp = AsyncMock(return_value={
        "summary": "Voici un résumé de test des actualités.",
        "tokens": 50
    })
    mock.format_sources_message = Mock(return_value="Sources:\n[1] example.com")
    mock.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock

@pytest.fixture
def mock_perplexica_service():
    """Mock Perplexica service"""
    mock = AsyncMock()
    mock.search_multi_interests = AsyncMock(return_value={
        "success": True,
        "interests_covered": ["politique", "technologie"],
        "sources": [
            {
                "title": "Test Article",
                "url": "https://example.com/test",
                "content": "Test content",
                "quality_score": 9
            }
        ]
    })
    mock.format_for_whatsapp = Mock(return_value={
        "summary": "Voici un résumé de test.",
        "sources": [
            {"title": "Test Article", "url": "https://example.com/test"}
        ]
    })
    return mock

@pytest.fixture
def mock_tts_service():
    """Mock TTS service"""
    mock = AsyncMock()
    mock.text_to_speech = AsyncMock(return_value="cache/audio/test_audio.ogg")
    mock.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock

@pytest.fixture
def mock_cache():
    """Mock Redis cache"""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    return mock

@pytest.fixture
def api_client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)

@pytest.fixture
def mock_orchestrator(mock_whatsapp_service, mock_llm_service,
                      mock_perplexica_service, mock_tts_service):
    """Create a mock orchestrator with all services"""
    from app.services.orchestrator import MessageOrchestrator

    orchestrator = MessageOrchestrator()
    orchestrator.whatsapp_service = mock_whatsapp_service
    orchestrator.llm_service = mock_llm_service
    orchestrator.perplexica_service = mock_perplexica_service
    orchestrator.tts_service = mock_tts_service

    return orchestrator

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Setup test environment variables"""
    monkeypatch.setenv("WHATSAPP_TOKEN", "test_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test_verify")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    monkeypatch.setenv("PPLX_API_KEY", "test_pplx_key")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ENVIRONMENT", "test")
