"""Pydantic schemas for API validation"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema"""
    phone_number: str
    name: Optional[str] = None
    timezone: str = "Europe/Paris"
    language: str = "fr"


class UserCreate(UserBase):
    """Schema for creating a user"""
    pass


class UserResponse(UserBase):
    """User response schema"""
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class VoiceProfileBase(BaseModel):
    """Base voice profile schema"""
    voice_name: str
    is_default: bool = False


class VoiceProfileCreate(VoiceProfileBase):
    """Schema for creating a voice profile"""
    voice_file_path: str


class VoiceProfileResponse(VoiceProfileBase):
    """Voice profile response schema"""
    id: int
    user_id: int
    voice_file_path: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class PreferenceBase(BaseModel):
    """Base preference schema"""
    keywords: Optional[List[str]] = []
    daily_schedule: Optional[str] = None
    channels: List[str] = ["whatsapp"]
    max_results: int = 5
    summary_style: str = "concise"
    
    @validator('daily_schedule')
    def validate_time_format(cls, v):
        if v:
            try:
                datetime.strptime(v, "%H:%M")
            except ValueError:
                raise ValueError("Time must be in HH:MM format")
        return v
    
    @validator('summary_style')
    def validate_summary_style(cls, v):
        allowed = ["concise", "detailed", "bullet_points"]
        if v not in allowed:
            raise ValueError(f"Summary style must be one of {allowed}")
        return v


class PreferenceUpdate(PreferenceBase):
    """Schema for updating preferences"""
    voice_profile_id: Optional[int] = None


class MessageRequest(BaseModel):
    """WhatsApp message request schema"""
    phone_number: str
    text: str
    message_type: str = "text"
    media_id: Optional[str] = None
    media_url: Optional[str] = None


class SearchRequest(BaseModel):
    """Search request schema"""
    query: str
    max_results: int = Field(default=5, ge=1, le=20)
    language: str = "fr"
    categories: str = "general"


class SearchResult(BaseModel):
    """Search result schema"""
    title: str
    url: str
    snippet: str
    full_content: Optional[str] = None
    score: float = 0.0


class SearchResponse(BaseModel):
    """Search response schema"""
    query: str
    results: List[SearchResult]
    total: int
    processing_time: float


class SummaryRequest(BaseModel):
    """Summary generation request schema"""
    search_results: Dict[str, Any]
    query: str
    style: str = "concise"
    max_length: int = 500


class TTSRequest(BaseModel):
    """TTS generation request schema"""
    text: str
    voice_profile_id: Optional[int] = None
    language: str = "fr"
    output_format: str = "mp3"


class ConversationResponse(BaseModel):
    """Conversation response schema"""
    id: int
    query: str
    response_text: Optional[str]
    response_audio_url: Optional[str]
    sources: Optional[List[Dict[str, str]]]
    tokens_used: Optional[int]
    processing_time: Optional[float]
    created_at: datetime
    
    class Config:
        from_attributes = True


class WebhookVerification(BaseModel):
    """WhatsApp webhook verification schema"""
    hub_mode: str = Field(alias="hub.mode")
    hub_verify_token: str = Field(alias="hub.verify_token")
    hub_challenge: str = Field(alias="hub.challenge")


class WhatsAppMessage(BaseModel):
    """WhatsApp message structure"""
    from_number: str = Field(alias="from")
    message_id: str = Field(alias="id")
    timestamp: str
    text: Optional[Dict[str, str]] = None
    audio: Optional[Dict[str, str]] = None
    type: str
    
    class Config:
        populate_by_name = True


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)