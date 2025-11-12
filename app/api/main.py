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
from app.api.schemas import (
    RootResponse, HealthCheckResponse, WebhookResponse,
    SearchTestRequest, SearchTestResponse,
    PipelineTestRequest, PipelineTestResponse,
    TTSTestRequest, TTSTestResponse,
    MessageTestRequest, MessageTestResponse,
    BriefingTestRequest, BriefingTestResponse,
    ErrorResponse
)

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

# Create FastAPI app with comprehensive API documentation
app = FastAPI(
    title="Noto - AI News Bot API",
    description="""
## Noto - Agent IA d'information personnalisé

Pipeline IA de bout en bout pour collecter, analyser et délivrer des briefings d'actualités personnalisés via WhatsApp.

### Fonctionnalités principales

* **Collecte d'actualités** - Recherche IA via Perplexity Sonar et Perplexica
* **Analyse intelligente** - Reconnaissance d'entités nommées (NER) et scoring d'importance
* **Synthèse personnalisée** - Génération de résumés via GPT-4o-mini
* **Synthèse vocale** - Clonage vocal avec XTTS-v2
* **Livraison WhatsApp** - Intégration WhatsApp Business API

### Architecture

Le système implémente un pipeline en 4 étapes :
1. **Collecte** : Perplexica/Sonar recherche les actualités récentes
2. **Traitement** : Extraction de contenu + NER + scoring d'importance
3. **Synthèse** : GPT-4o-mini génère des résumés personnalisés
4. **Livraison** : TTS + envoi sur WhatsApp

### Stack technique

- FastAPI (async, production-ready)
- SQLAlchemy + SQLite
- Redis cache
- Perplexity Sonar API
- OpenAI GPT-4o-mini
- SpaCy NER
- XTTS-v2 TTS
- WhatsApp Business API
    """,
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "Nicolas Angougeard",
        "url": "https://github.com/Aguern/Noto",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    tags_metadata=[
        {
            "name": "System",
            "description": "Endpoints système pour vérifier le statut et la santé de l'API"
        },
        {
            "name": "WhatsApp",
            "description": "Endpoints webhook pour l'intégration WhatsApp Business API"
        },
        {
            "name": "Testing",
            "description": "Endpoints de test pour développement et debugging (désactiver en production)"
        }
    ]
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

# Health check endpoints
@app.get(
    "/",
    response_model=RootResponse,
    tags=["System"],
    summary="Root endpoint",
    description="Retourne les informations basiques sur l'API et son statut"
)
async def root():
    """
    Endpoint racine qui fournit les informations de base sur l'API.

    Utilisé pour vérifier rapidement que l'API est accessible.
    """
    return {
        "service": "Noto - AI News Bot",
        "status": "running",
        "version": "1.0.0"
    }

@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["System"],
    summary="Health check complet",
    description="Vérifie l'état de santé de tous les services (base de données, cache, APIs externes, scheduler)"
)
async def health_check():
    """
    Health check complet qui vérifie l'état de tous les composants du système.

    Retourne le statut détaillé de :
    - Base de données SQLite
    - Cache Redis
    - APIs externes (WhatsApp, Perplexity, OpenAI)
    - Scheduler service

    Utilisé pour monitoring et alertes en production.
    """
    try:
        health_status = await orchestrator.health_check()
        # Add scheduler status
        scheduler_status = scheduler_service.get_active_schedules()

        return {
            "status": "healthy",
            "timestamp": "2025-01-12T10:30:00Z",
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
@app.get(
    "/webhook",
    tags=["WhatsApp"],
    summary="Vérification webhook WhatsApp",
    description="Endpoint de vérification appelé par WhatsApp pour valider le webhook",
    responses={
        200: {"description": "Webhook vérifié avec succès"},
        403: {"description": "Token de vérification invalide", "model": ErrorResponse},
        400: {"description": "Requête invalide", "model": ErrorResponse}
    }
)
async def verify_webhook(request: Request):
    """
    Vérification du webhook WhatsApp Business API.

    WhatsApp envoie une requête GET avec les paramètres :
    - `hub.mode` : doit être "subscribe"
    - `hub.verify_token` : token configuré dans .env (WHATSAPP_VERIFY_TOKEN)
    - `hub.challenge` : valeur à retourner pour confirmer la vérification

    Cette étape est nécessaire lors de la configuration initiale du webhook dans Meta Developer Console.
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
@app.post(
    "/webhook",
    response_model=WebhookResponse,
    tags=["WhatsApp"],
    summary="Réception de messages WhatsApp",
    description="Endpoint webhook qui reçoit les messages entrants depuis WhatsApp Business API",
    responses={
        200: {"description": "Message traité avec succès", "model": WebhookResponse}
    }
)
@app.post(
    "/webhook/whatsapp",
    response_model=WebhookResponse,
    tags=["WhatsApp"],
    summary="Réception de messages WhatsApp (route alternative)",
    include_in_schema=False
)
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Gère les messages entrants depuis WhatsApp Business API.

    Format du payload WhatsApp :
    ```json
    {
      "entry": [{
        "changes": [{
          "value": {
            "messages": [{
              "from": "+33612345678",
              "type": "text",
              "text": {"body": "actualités tech"}
            }]
          }
        }]
      }]
    }
    ```

    Le traitement du message est effectué en arrière-plan (BackgroundTasks) pour :
    - Retourner immédiatement un 200 OK à WhatsApp (requis)
    - Éviter les timeouts sur les traitements longs (recherche + LLM + TTS)
    - Permettre le traitement concurrent de plusieurs messages

    Le pipeline complet est géré par MessageOrchestrator :
    1. Routing de commandes (/start, /help, /keywords, etc.)
    2. Gestion d'état utilisateur (onboarding, preferences)
    3. Recherche d'actualités (Perplexica/Sonar)
    4. Génération de résumé (GPT-4o-mini)
    5. Synthèse vocale (XTTS-v2)
    6. Envoi sur WhatsApp
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
@app.post(
    "/test/search",
    response_model=SearchTestResponse,
    tags=["Testing"],
    summary="Test recherche Perplexica",
    description="Teste la fonctionnalité de recherche IA Perplexica sans passer par WhatsApp"
)
async def test_search(body: SearchTestRequest):
    """
    Test de la recherche Perplexica sans interaction WhatsApp.

    Permet de tester rapidement la recherche d'actualités avec Perplexica en local.

    Exemple de requête :
    ```json
    {
      "query": "actualités intelligence artificielle"
    }
    ```

    Retourne les résultats de recherche bruts depuis Perplexica.
    """
    try:
        query = body.query

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

@app.post(
    "/test/pipeline",
    response_model=PipelineTestResponse,
    tags=["Testing"],
    summary="Test pipeline complet",
    description="Teste le pipeline complet : recherche multi-intérêts + formatage pour WhatsApp"
)
async def test_pipeline(body: PipelineTestRequest):
    """
    Test du pipeline complet Perplexica avec recherche multi-intérêts.

    Permet de tester :
    - Recherche multi-intérêts (plusieurs sujets en parallèle)
    - Formatage des résultats pour WhatsApp
    - Personnalisation par utilisateur

    Exemple de requête :
    ```json
    {
      "query": "actualités",
      "interests": ["tech", "IA", "startup"]
    }
    ```

    Retourne à la fois les résultats bruts et le résumé formaté.
    """
    try:
        query = body.query
        interests = body.interests

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

@app.post(
    "/test/tts",
    response_model=TTSTestResponse,
    tags=["Testing"],
    summary="Test synthèse vocale",
    description="Teste la génération audio avec XTTS-v2 (text-to-speech)"
)
async def test_tts(body: TTSTestRequest):
    """
    Test de la synthèse vocale (TTS) avec XTTS-v2.

    Convertit un texte en audio avec clonage vocal neural.

    Exemple de requête :
    ```json
    {
      "text": "Voici les actualités tech du jour"
    }
    ```

    Retourne :
    - Le chemin local du fichier audio généré
    - L'URL pour accéder à l'audio via `/audio/`
    - Le texte converti

    Format audio : OGG Opus (optimisé pour WhatsApp)
    """
    try:
        text = body.text

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

@app.post(
    "/test/message",
    response_model=MessageTestResponse,
    tags=["Testing"],
    summary="Test traitement de message",
    description="Simule un message WhatsApp complet pour tester le pipeline end-to-end"
)
async def test_message(body: MessageTestRequest, background_tasks: BackgroundTasks):
    """
    Test du traitement complet d'un message (simulation WhatsApp).

    Simule un message WhatsApp et l'envoie dans le pipeline complet :
    1. Parsing du message
    2. Routing de commande ou recherche d'actualités
    3. Génération de résumé (si applicable)
    4. TTS (si activé)
    5. Envoi sur WhatsApp

    Exemple de requête :
    ```json
    {
      "phone_number": "+33612345678",
      "text": "actualités tech aujourd'hui"
    }
    ```

    Le traitement est asynchrone (background task) et retourne immédiatement.
    Vérifiez les logs ou WhatsApp pour voir le résultat.
    """
    try:
        phone_number = body.phone_number
        text = body.text

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

@app.post(
    "/test/briefing",
    response_model=BriefingTestResponse,
    tags=["Testing"],
    summary="Test génération de briefing",
    description="Génère un briefing d'actualités complet pour un sujet donné"
)
async def test_briefing(body: BriefingTestRequest, background_tasks: BackgroundTasks):
    """
    Test de la génération d'un briefing d'actualités complet.

    Génère un briefing personnalisé sur un sujet spécifique.
    Pipeline complet :
    1. Recherche d'actualités (Perplexica/Sonar)
    2. Extraction et scoring de contenu
    3. Génération de résumé (GPT-4o-mini)
    4. Synthèse vocale (XTTS-v2)
    5. Envoi sur WhatsApp

    Exemple de requête :
    ```json
    {
      "phone_number": "+33612345678",
      "topic": "tech et innovation"
    }
    ```

    Le briefing est généré en arrière-plan et envoyé sur WhatsApp.
    Durée estimée : 8-15 secondes.
    """
    try:
        phone_number = body.phone_number
        topic = body.topic

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