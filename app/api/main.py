"""Main FastAPI application"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from dotenv import load_dotenv

from app.services.orchestrator import MessageOrchestrator
from app.services.scheduler_service import scheduler_service
from app.models.database import init_db, get_db, User
from app.utils.cache import cache

load_dotenv()

# Initialize orchestrator
orchestrator = MessageOrchestrator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Perplexity WhatsApp Bot...")
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Connect to Redis cache
    await cache.connect()
    logger.info("Cache connected")
    
    # Setup and start scheduler
    scheduler_service.set_orchestrator(orchestrator)
    scheduler_service.start_scheduler()
    logger.info("Scheduler service started")
    
    # Yield control to application
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    scheduler_service.stop_scheduler()
    await cache.close()

# Create FastAPI app
app = FastAPI(
    title="Perplexity WhatsApp Bot",
    description="AI-powered WhatsApp bot with web search, voice synthesis, and intelligent responses",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (audio files)
if not os.path.exists("cache/audio"):
    os.makedirs("cache/audio", exist_ok=True)

app.mount("/audio", StaticFiles(directory="cache/audio"), name="audio")

# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Perplexity WhatsApp Bot",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    try:
        health_status = await orchestrator.health_check()
        # Add scheduler status
        scheduler_status = scheduler_service.get_active_schedules()
        
        return {
            "status": "healthy",
            "timestamp": "2025-08-27",  # Current timestamp
            "services": health_status,
            "scheduler": scheduler_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# WhatsApp webhook verification
@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Verify WhatsApp webhook
    
    WhatsApp will send GET requests to verify the webhook URL
    """
    try:
        # Get query parameters
        mode = request.query_params.get("hub.mode")
        verify_token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"Webhook verification request: mode={mode}, token_provided={bool(verify_token)}")
        
        # Verify token
        expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN")
        
        if mode == "subscribe" and verify_token == expected_token:
            logger.info("Webhook verification successful")
            return Response(content=challenge, media_type="text/plain")
        else:
            logger.warning(f"Webhook verification failed: mode={mode}, token_match={verify_token == expected_token}")
            raise HTTPException(status_code=403, detail="Forbidden")
            
    except Exception as e:
        logger.error(f"Webhook verification error: {e}")
        raise HTTPException(status_code=400, detail="Bad Request")

# WhatsApp webhook for receiving messages
@app.post("/webhook")
@app.post("/webhook/whatsapp")  # Alternative route for WhatsApp
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp messages
    
    This endpoint receives webhook POST requests from WhatsApp
    when users send messages to the bot
    """
    try:
        # Parse request body
        body = await request.json()
        logger.info(f"Received webhook: {body}")
        
        # Extract message data from WhatsApp webhook format
        if "entry" not in body:
            return {"status": "ok"}  # Ignore non-message webhooks
        
        for entry in body["entry"]:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # Handle status updates (message delivered, read, etc.)
                if "statuses" in value:
                    logger.info("Received message status update")
                    continue
                
                # Handle incoming messages
                messages = value.get("messages", [])
                for message in messages:
                    phone_number = message["from"]
                    
                    # Add message processing to background tasks
                    # This allows the webhook to return immediately
                    background_tasks.add_task(
                        orchestrator.process_message,
                        phone_number,
                        message
                    )
                    
                    logger.info(f"Queued message processing for {phone_number}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        # Always return 200 to WhatsApp to avoid retries
        return {"status": "error", "message": str(e)}

# Manual testing endpoints (for development)
@app.post("/test/search")
async def test_search(request: Request):
    """Test Perplexica search functionality"""
    try:
        body = await request.json()
        query = body.get("query", "actualités tech")
        
        if not orchestrator.use_perplexica or not orchestrator.perplexica_service:
            raise HTTPException(status_code=503, detail="Perplexica not configured")
        
        search_result = await orchestrator.perplexica_service.search_with_ai(
            query=query,
            focus_mode="webSearch",
            language="fr"
        )
        return search_result
        
    except Exception as e:
        logger.error(f"Perplexica test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test/pipeline")
async def test_pipeline(request: Request):
    """Test complete Perplexica pipeline"""
    try:
        body = await request.json()
        query = body.get("query", "actualités économie France")
        interests = body.get("interests", ["économie", "tech"])
        
        if not orchestrator.use_perplexica or not orchestrator.perplexica_service:
            raise HTTPException(status_code=503, detail="Perplexica not configured")
        
        # Test multi-interest search
        search_result = await orchestrator.perplexica_service.search_multi_interests(
            interests=interests,
            base_query="actualités",
            max_results_per_interest=2
        )
        
        if search_result.get("success"):
            # Format for WhatsApp
            formatted_result = orchestrator.perplexica_service.format_for_whatsapp(
                search_result, "TestUser", interests
            )
            return {
                "success": True,
                "raw_search": search_result,
                "formatted_summary": formatted_result
            }
        else:
            return {"success": False, "error": search_result.get("error", "Unknown error")}
        
    except Exception as e:
        logger.error(f"Pipeline test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test/tts")
async def test_tts(request: Request):
    """Test TTS functionality"""
    try:
        body = await request.json()
        text = body.get("text", "Bonjour, ceci est un test de synthèse vocale.")
        
        audio_path = await orchestrator.tts_service.text_to_speech(text)
        
        if audio_path:
            # Return URL to access the audio file
            audio_url = f"/audio/{os.path.basename(audio_path)}"
            return {
                "status": "success",
                "audio_path": audio_path,
                "audio_url": audio_url,
                "text": text
            }
        else:
            return {"status": "failed", "error": "TTS generation failed"}
            
    except Exception as e:
        logger.error(f"TTS test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test/message")
async def test_message(request: Request, background_tasks: BackgroundTasks):
    """Test complete message processing pipeline"""
    try:
        body = await request.json()
        phone_number = body.get("phone_number", "+1234567890")
        text = body.get("text", "latest AI news")
        
        # Create mock WhatsApp message format
        mock_message = {
            "from": phone_number,
            "id": "test_message_id",
            "timestamp": "1693142400",
            "type": "text",
            "text": {
                "body": text
            }
        }
        
        # Process message in background
        background_tasks.add_task(
            orchestrator.process_message,
            phone_number,
            mock_message
        )
        
        return {
            "status": "queued",
            "message": f"Message processing queued for {phone_number}"
        }
        
    except Exception as e:
        logger.error(f"Message test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test/briefing")
async def test_briefing(request: Request, background_tasks: BackgroundTasks):
    """Test news briefing generation"""
    try:
        body = await request.json()
        phone_number = body.get("phone_number", os.getenv("WHATSAPP_TEST_NUMBER", "+1234567890"))
        topic = body.get("topic", "actualités France")
        
        # Get or create test user
        db = next(get_db())
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if not user:
            user = User(
                phone_number=phone_number,
                name="Test User",
                language="fr",
                timezone="Europe/Paris"
            )
            db.add(user)
            db.commit()
        
        # Generate brief in background
        background_tasks.add_task(
            orchestrator.generate_daily_brief,
            db,
            user,
            topic
        )
        
        return {
            "status": "generating",
            "message": f"Brief generation started for topic: {topic}"
        }
        
    except Exception as e:
        logger.error(f"Briefing test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'db' in locals():
            db.close()

# Error handlers
from fastapi.responses import JSONResponse

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found", "path": str(request.url)}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )

if __name__ == "__main__":
    import uvicorn
    
    # Configure logging
    logger.info("Starting Perplexity WhatsApp Bot server...")
    
    # Run server
    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        log_level="info"
    )