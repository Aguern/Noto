"""API response schemas for OpenAPI documentation"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    """Status of an individual service"""
    name: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status (operational, degraded, down)")
    details: Optional[str] = Field(None, description="Additional status details")


class HealthCheckResponse(BaseModel):
    """Health check endpoint response"""
    status: str = Field(..., description="Overall system status", example="healthy")
    timestamp: str = Field(..., description="Health check timestamp", example="2025-01-12T10:30:00Z")
    services: Dict[str, Any] = Field(..., description="Status of individual services")
    scheduler: Dict[str, Any] = Field(..., description="Scheduler service status")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-01-12T10:30:00Z",
                "services": {
                    "database": "connected",
                    "cache": "connected",
                    "whatsapp_api": "operational"
                },
                "scheduler": {
                    "active_schedules": 3,
                    "status": "running"
                }
            }
        }


class RootResponse(BaseModel):
    """Root endpoint response"""
    service: str = Field(..., description="Service name", example="Noto - AI News Bot")
    status: str = Field(..., description="Service status", example="running")
    version: str = Field(..., description="API version", example="1.0.0")


class WebhookVerificationResponse(BaseModel):
    """Webhook verification response"""
    status: str = Field(..., description="Verification status", example="verified")


class WebhookResponse(BaseModel):
    """Webhook processing response"""
    status: str = Field(..., description="Processing status", example="ok")
    message: Optional[str] = Field(None, description="Optional message or error details")


class SearchTestRequest(BaseModel):
    """Test search request body"""
    query: str = Field(
        default="actualités tech",
        description="Search query",
        example="actualités intelligence artificielle"
    )


class SearchTestResponse(BaseModel):
    """Search test response"""
    success: bool = Field(..., description="Whether the search was successful")
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Search results")
    error: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "results": [
                    {
                        "title": "OpenAI lance GPT-5",
                        "source": "TechCrunch",
                        "url": "https://techcrunch.com/...",
                        "content": "OpenAI annonce..."
                    }
                ]
            }
        }


class PipelineTestRequest(BaseModel):
    """Pipeline test request body"""
    query: str = Field(
        default="actualités économie France",
        description="Base query for news search",
        example="actualités technologie"
    )
    interests: List[str] = Field(
        default=["économie", "tech"],
        description="List of user interests",
        example=["IA", "startup", "crypto"]
    )


class PipelineTestResponse(BaseModel):
    """Pipeline test response"""
    success: bool = Field(..., description="Whether the pipeline completed successfully")
    raw_search: Optional[Dict[str, Any]] = Field(None, description="Raw search results")
    formatted_summary: Optional[str] = Field(None, description="Formatted summary for WhatsApp")
    error: Optional[str] = Field(None, description="Error message if failed")


class TTSTestRequest(BaseModel):
    """TTS test request body"""
    text: str = Field(
        default="Bonjour, ceci est un test de synthèse vocale.",
        description="Text to convert to speech",
        example="Voici les actualités tech du jour"
    )


class TTSTestResponse(BaseModel):
    """TTS test response"""
    status: str = Field(..., description="TTS generation status", example="success")
    audio_path: Optional[str] = Field(None, description="Local path to audio file")
    audio_url: Optional[str] = Field(None, description="URL to access audio file", example="/audio/tts_123456.ogg")
    text: str = Field(..., description="Text that was converted to speech")
    error: Optional[str] = Field(None, description="Error message if failed")


class MessageTestRequest(BaseModel):
    """Message test request body"""
    phone_number: str = Field(
        default="+1234567890",
        description="Phone number to send message to",
        example="+33612345678"
    )
    text: str = Field(
        default="latest AI news",
        description="Message text",
        example="actualités tech aujourd'hui"
    )


class MessageTestResponse(BaseModel):
    """Message test response"""
    status: str = Field(..., description="Processing status", example="queued")
    message: str = Field(..., description="Status message", example="Message processing queued for +33612345678")


class BriefingTestRequest(BaseModel):
    """Briefing test request body"""
    phone_number: str = Field(
        default="+1234567890",
        description="Phone number for test user",
        example="+33612345678"
    )
    topic: str = Field(
        default="actualités France",
        description="Topic for the briefing",
        example="tech et innovation"
    )


class BriefingTestResponse(BaseModel):
    """Briefing test response"""
    status: str = Field(..., description="Generation status", example="generating")
    message: str = Field(..., description="Status message", example="Brief generation started for topic: tech")


class ErrorResponse(BaseModel):
    """Generic error response"""
    error: str = Field(..., description="Error type or message", example="Internal server error")
    detail: Optional[str] = Field(None, description="Detailed error information")
    path: Optional[str] = Field(None, description="Request path that caused the error")
