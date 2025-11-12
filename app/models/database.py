"""Database models and configuration"""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./perplexity_bot.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    timezone = Column(String, default="Europe/Paris")
    language = Column(String, default="fr")
    is_active = Column(Boolean, default=True)
    
    # Onboarding state management
    onboarding_state = Column(String, default="completed")  # completed, welcome, keywords, validation, schedule, voice, final
    onboarding_data = Column(Text)  # JSON data for onboarding flow
    is_onboarded = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    voice_profiles = relationship("VoiceProfile", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("Preference", uselist=False, back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class VoiceProfile(Base):
    """Voice profile for TTS cloning"""
    __tablename__ = "voice_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    voice_name = Column(String, nullable=False)
    voice_file_path = Column(String, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="voice_profiles")


class Preference(Base):
    """User preferences and settings"""
    __tablename__ = "preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    keywords = Column(Text)  # JSON array of keywords
    daily_schedule = Column(String)  # Time for daily summary (HH:MM format)
    channels = Column(Text, default='["whatsapp"]')  # JSON array of channels
    voice_profile_id = Column(Integer, ForeignKey("voice_profiles.id"))
    max_results = Column(Integer, default=5)
    summary_style = Column(String, default="concise")  # concise, detailed, bullet_points
    
    # Relationships
    user = relationship("User", back_populates="preferences")


class Conversation(Base):
    """Conversation history"""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    query = Column(Text, nullable=False)
    response_text = Column(Text)
    response_audio_url = Column(String)
    sources = Column(Text)  # JSON array of sources
    tokens_used = Column(Integer)
    processing_time = Column(Float)  # in seconds
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="conversations")


class Cache(Base):
    """Cache for search results and audio files"""
    __tablename__ = "cache"
    
    id = Column(Integer, primary_key=True, index=True)
    query_hash = Column(String, unique=True, index=True, nullable=False)
    cache_type = Column(String, nullable=False)  # 'search' or 'audio'
    results = Column(Text)  # JSON for search results
    file_path = Column(String)  # Path for audio files
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Create tables
def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    # Create tables when running this file directly
    init_db()
    print("Database tables created successfully!")