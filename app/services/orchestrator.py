"""Main orchestrator for coordinating all services"""
import os
import json
from typing import Dict, Optional, List
from datetime import datetime, time
import re
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import User, VoiceProfile, Preference, Conversation, get_db
from app.services.llm_service import LLMService
from app.services.tts_service import TTSService
from app.services.whatsapp_service import WhatsAppService
from app.services.perplexica_service import PerplexicaService
from app.services.news.collector_sonar import NewsCollector
from app.services.news.summarizer_gpt5 import NewsSummarizer
from app.utils.validate import NewsValidator

# Constants for search configuration
MAX_RESULTS_PER_INTEREST = 1  # Optimized to avoid API timeouts while maintaining quality
DEFAULT_MAX_RESULTS = 5  # Default number of search results if user has no preferences
MINIMUM_NEWS_ITEMS = 3  # Minimum number of news items required for a valid briefing
NEWS_BRIEF_MAX_WORDS = 250  # Maximum words for text brief
NEWS_BRIEF_AUDIO_WORDS = 140  # Shorter word count for audio version


class MessageOrchestrator:
    """Orchestrates the complete message processing pipeline for WhatsApp AI Bot.

    This class serves as the central coordinator for all incoming WhatsApp messages,
    managing the flow from message reception to response delivery. It implements
    the command pattern for message routing and coordinates multiple AI services
    (Perplexica search, LLM processing, TTS generation) to deliver personalized
    news briefings and search responses.

    Architecture:
        WhatsApp Message → Orchestrator → [Perplexica, LLM, TTS] → WhatsApp Response

    The orchestrator implements:
        - User onboarding flow with state machine
        - Command routing (/help, /start, /keywords, etc.)
        - Multi-interest search orchestration via Perplexica
        - Conversation logging and analytics
        - Error handling and fallback strategies

    Attributes:
        llm_service (LLMService): Service for LLM operations (summarization, formatting)
        tts_service (TTSService): Service for text-to-speech audio generation
        whatsapp_service (WhatsAppService): Service for WhatsApp API communication
        perplexica_service (PerplexicaService): AI-powered search service (UNIQUE pipeline)
        news_collector (NewsCollector): News collection using Perplexity Sonar
        news_summarizer (NewsSummarizer): GPT-based news summarization
        commands (Dict): Mapping of command strings to handler methods
        onboarding_handlers (Dict): State machine handlers for user onboarding

    Example:
        >>> orchestrator = MessageOrchestrator()
        >>> await orchestrator.process_message(
        ...     phone_number="+33612345678",
        ...     message_data={"type": "text", "text": {"body": "actualités tech"}}
        ... )

    Note:
        Perplexica is configured as the UNIQUE search pipeline. Traditional search
        has been deprecated per ARCHITECTURE_UNIQUE.md specifications.
    """

    def __init__(self):
        # Initialize services
        self.llm_service = LLMService()
        self.tts_service = TTSService()
        self.whatsapp_service = WhatsAppService()
        
        # Initialize Perplexica as UNIQUE search system
        self.use_perplexica = os.getenv("USE_PERPLEXICA", "true").lower() == "true"
        if self.use_perplexica:
            self.perplexica_service = PerplexicaService()
            logger.info("Perplexica integration enabled as UNIQUE pipeline")
        else:
            self.perplexica_service = None
            logger.error("WARNING: Perplexica disabled - this breaks the main functionality!")
        
        # Initialize news briefing services
        self.news_collector = NewsCollector()
        self.news_summarizer = NewsSummarizer()
        self.news_validator = NewsValidator()
        
        # Command handlers
        self.commands = {
            "/start": self._handle_start_command,
            "/help": self._handle_help_command,
            "/voice": self._handle_voice_command,
            "/keywords": self._handle_keywords_command,
            "/schedule": self._handle_schedule_command,
            "/stats": self._handle_stats_command,
            "/clear": self._handle_clear_command,
            "/pref": self._handle_pref_command,
            "/stop": self._handle_stop_command,
            "/briefing": self._handle_briefing_command,
            "/centres": self._handle_centres_command,
            "/frequence": self._handle_frequence_command,
            "/audio": self._handle_audio_command
        }
        
        # Onboarding state handlers
        self.onboarding_handlers = {
            "welcome": self._handle_onboarding_welcome,
            "keywords": self._handle_onboarding_keywords,
            "validation": self._handle_onboarding_validation,
            "schedule": self._handle_onboarding_schedule,
            "voice": self._handle_onboarding_voice,
            "final_validation": self._handle_onboarding_final_validation,
            "final": self._handle_onboarding_final
        }
    
    async def process_message(
        self,
        phone_number: str,
        message_data: Dict[str, any]
    ) -> None:
        """Process incoming WhatsApp message through the complete AI pipeline.

        This is the main entry point for all incoming WhatsApp messages. It handles:
        - User creation and retrieval
        - Message type routing (text, audio, or unsupported types)
        - Error handling with graceful fallback messages
        - Database session management

        The method delegates to specialized handlers based on message type and
        user state (onboarding, command, or standard query).

        Args:
            phone_number: User's phone number in E.164 format (e.g., "+33612345678")
            message_data: WhatsApp message payload containing:
                - type (str): Message type ("text", "audio", etc.)
                - text (dict, optional): Text message with {"body": "content"}
                - audio (dict, optional): Audio message with {"id": "media_id"}
                - timestamp (str): Unix timestamp of message

        Returns:
            None. Responses are sent asynchronously via WhatsApp service.

        Raises:
            No exceptions are raised. All errors are caught and result in error
            messages sent to the user via WhatsApp.

        Example:
            >>> message_data = {
            ...     "type": "text",
            ...     "text": {"body": "actualités tech"},
            ...     "timestamp": "1234567890"
            ... }
            >>> await orchestrator.process_message("+33612345678", message_data)

        Note:
            This method is designed to return quickly to WhatsApp webhooks (< 10s)
            to avoid timeout issues. Long-running operations should be optimized
            or moved to background tasks.
        """
        start_time = datetime.utcnow()
        
        try:
            # Get or create user
            db = next(get_db())
            user = await self._get_or_create_user(db, phone_number)
            
            # Extract message content
            message_type = message_data.get("type", "text")
            
            if message_type == "text":
                text = message_data.get("text", {}).get("body", "")
                await self._process_text_message(db, user, text, start_time)
                
            elif message_type == "audio":
                audio_id = message_data.get("audio", {}).get("id")
                await self._process_audio_message(db, user, audio_id)
                
            else:
                await self.whatsapp_service.send_text_message(
                    phone_number,
                    "❌ Type de message non supporté. Envoyez du texte ou de l'audio."
                )
            
        except Exception as e:
            logger.error(f"Error processing message from {phone_number}: {e}")
            await self.whatsapp_service.send_text_message(
                phone_number,
                "❌ Une erreur s'est produite. Réessayez dans quelques instants."
            )
        finally:
            if 'db' in locals():
                db.close()
    
    async def _process_text_message(
        self, 
        db: Session, 
        user: User, 
        text: str, 
        start_time: datetime
    ):
        """Process text message"""
        # Handle commands
        if text.startswith("/"):
            command = text.split()[0].lower()
            if command in self.commands:
                await self.commands[command](db, user, text)
                return
            else:
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "❓ Commande inconnue. Tapez /help pour voir les commandes disponibles."
                )
                return
        
        # Check if user is in onboarding flow
        if user.onboarding_state and user.onboarding_state != "completed":
            await self._handle_onboarding_message(db, user, text)
            return
        
        # Check if this is a news query
        if self.news_validator.is_news_query(text):
            # Extract topic from query
            topic = self._extract_topic_from_query(text)
            await self.generate_daily_brief(db, user, topic)
            return
        
        # Process as search query
        await self._process_search_query(db, user, text, start_time)
    
    async def _process_search_query(
        self, 
        db: Session, 
        user: User, 
        query: str, 
        start_time: datetime
    ):
        """Process search query through the full pipeline"""
        try:
            logger.info(f"Processing search query from {user.phone_number}: {query}")
            
            # Get user preferences
            preferences = db.query(Preference).filter(Preference.user_id == user.id).first()
            max_results = preferences.max_results if preferences else DEFAULT_MAX_RESULTS
            summary_style = preferences.summary_style if preferences else "concise"
            
            # Step 1: Multi-interest search (Perplexica or traditional)
            logger.info("Step 1: Searching web by interests...")
            
            # Get user keywords for targeted searches
            onboarding_data = json.loads(user.onboarding_data or "{}")
            user_keywords = onboarding_data.get("keywords", ["actualités"])
            
            # PIPELINE UNIQUE : Perplexica seulement (suppression du pipeline traditionnel)
            logger.info("Using Perplexica AI search (UNIQUE PIPELINE)")
            
            # Vérifier que Perplexica est activé et disponible
            if not self.use_perplexica or not self.perplexica_service:
                logger.error("Perplexica not configured - this is the only supported pipeline")
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "Service temporairement indisponible. Veuillez réessayer plus tard."
                )
                return
            
            # Effectuer la recherche multi-intérêts via Perplexica
            perplexica_results = await self.perplexica_service.search_multi_interests(
                interests=user_keywords,
                base_query="actualités",
                max_results_per_interest=MAX_RESULTS_PER_INTEREST
            )
            
            # Vérifier le succès de la recherche
            if not perplexica_results.get("success") or not perplexica_results.get("interests_covered"):
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    f"Aucune actualité trouvée pour vos centres d'intérêt. Essayez plus tard."
                )
                return
            
            # Formatage pour WhatsApp/audio avec informations riches
            user_name = user.name if user.name != f"User_{user.phone_number[-4:]}" else "Nicolas"
            formatted_result = self.perplexica_service.format_for_whatsapp(
                perplexica_results, user_name, user_keywords
            )
            
            summary_text = formatted_result.get("summary")
            sources_data = formatted_result.get("sources", [])
            tokens_used = 0  # Perplexica doesn't expose token usage
            
            # Log des informations de débogage
            logger.info(f"Perplexica processed {len(perplexica_results.get('interests_covered', []))} interests")
            logger.info(f"Generated summary: {len(summary_text) if summary_text else 0} chars")
            logger.info(f"Sources found: {len(sources_data)}")
            
            # Step 3: Generate audio (optional)
            audio_path = None
            voice_profile = None
            
            if preferences and preferences.voice_profile_id:
                voice_profile = db.query(VoiceProfile).filter(
                    VoiceProfile.id == preferences.voice_profile_id
                ).first()
            
            logger.info("Step 3: Generating audio...")
            audio_path = await self.tts_service.text_to_speech(
                text=summary_text,
                voice_profile_path=voice_profile.voice_file_path if voice_profile else None,
                language=user.language
            )
            
            # Step 4: Send response
            logger.info("Step 4: Sending response...")
            if audio_path:
                # Send audio only (no text)
                await self.whatsapp_service.send_audio_message(
                    user.phone_number,
                    audio_path
                )
                
                # Send sources separately if available
                if sources_data:
                    sources_message = self.llm_service.format_sources_message(sources_data)
                    if sources_message:
                        await self.whatsapp_service.send_text_message(
                            user.phone_number,
                            sources_message
                        )
            else:
                # Fallback to text if no audio
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    summary_text
                )
            
            # Step 5: Log conversation
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            # Prepare search results for logging
            search_results = {
                "sources": sources_data,
                "interests_covered": perplexica_results.get("interests_covered", []),
                "success": True
            }
            await self._log_conversation(
                db, user, query, summary_text, search_results,
                tokens_used, processing_time, audio_path
            )
            
            logger.info(f"Query processed successfully in {processing_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Error processing search query: {e}")
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "❌ Erreur lors du traitement de votre recherche. Réessayez plus tard."
            )
    
    async def _process_audio_message(self, db: Session, user: User, audio_id: str):
        """Process audio message - voice cloning not supported"""
        try:
            logger.info(f"Audio message received from {user.phone_number} - voice cloning not supported")
            
            # Check if user is in onboarding voice step
            if user.onboarding_state == "voice":
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "Le clonage vocal n'est pas encore disponible. Nous utiliserons la voix par défaut.\n\nTapez 'passer' pour continuer."
                )
            else:
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "Le clonage vocal n'est pas disponible. Les résumés audio utilisent la voix par défaut."
                )
        
        except Exception as e:
            logger.error(f"Error processing audio message: {e}")
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "Erreur lors du traitement de l'audio."
            )
    
    async def _get_or_create_user(self, db: Session, phone_number: str) -> User:
        """Get existing user or create new one"""
        user = db.query(User).filter(User.phone_number == phone_number).first()
        
        if not user:
            user = User(
                phone_number=phone_number,
                name=f"User_{phone_number[-4:]}",  # Use last 4 digits as default name
                language="fr",
                timezone="Europe/Paris",
                onboarding_state="welcome",  # Start onboarding for new users
                is_onboarded=False,
                onboarding_data=json.dumps({})
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            logger.info(f"Created new user: {phone_number}")
            
            # Start onboarding flow
            await self._start_onboarding(db, user)
        
        return user
    
    async def _log_conversation(
        self,
        db: Session,
        user: User,
        query: str,
        response: str,
        search_results: Dict,
        tokens_used: int,
        processing_time: float,
        audio_url: Optional[str] = None
    ):
        """Log conversation to database"""
        try:
            conversation = Conversation(
                user_id=user.id,
                query=query,
                response_text=response,
                response_audio_url=audio_url,
                sources=json.dumps(search_results.get("results", [])),
                tokens_used=tokens_used,
                processing_time=processing_time
            )
            
            db.add(conversation)
            db.commit()
            
        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")
    
    # Onboarding handlers
    async def _start_onboarding(self, db: Session, user: User):
        """Start the onboarding flow"""
        welcome_message = """Bienvenue sur Noto.

Noto vous délivre des résumés d'actualités quotidiens personnalisés avec votre propre voix clonée.

Configuration requise :

*Étape 1/3 : Centres d'intérêt*

Quels sujets souhaitez-vous suivre dans vos résumés quotidiens ?

Exemples : politique française, économie, tech, sport, crypto

Envoyez vos sujets d'intérêt séparés par des virgules."""
        
        await self.whatsapp_service.send_text_message(user.phone_number, welcome_message)
        user.onboarding_state = "keywords"
        db.commit()
    
    async def _handle_onboarding_message(self, db: Session, user: User, text: str):
        """Handle message during onboarding flow"""
        handler = self.onboarding_handlers.get(user.onboarding_state)
        if handler:
            await handler(db, user, text)
        else:
            logger.error(f"Unknown onboarding state: {user.onboarding_state}")
            await self._complete_onboarding(db, user)
    
    async def _handle_onboarding_welcome(self, db: Session, user: User, text: str):
        """Handle welcome state - should not happen as we start from keywords directly"""
        # Move directly to keywords collection
        await self._handle_onboarding_keywords(db, user, text)
    
    async def _handle_onboarding_keywords(self, db: Session, user: User, text: str):
        """Handle keywords collection during onboarding"""
        # Ignore common greetings and wait for actual keywords
        greetings = ['bonjour', 'salut', 'hello', 'hi', 'hey', 'coucou', 'bonsoir']
        if text.lower().strip() in greetings:
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "Merci ! Maintenant, quels sujets vous intéressent ?\n\nExemples : tech, sport, économie, politique"
            )
            return
            
        if text.lower() in ['passer', 'skip', 'ignorer']:
            keywords = ["actualités", "tech"]  # Default keywords
        else:
            keywords = [k.strip() for k in text.split(",") if k.strip()]
            if not keywords:
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "Je n'ai pas compris vos centres d'intérêt. Pouvez-vous les reformuler ? (ex: tech, sport, crypto)"
                )
                return
        
        # Store in onboarding data
        onboarding_data = json.loads(user.onboarding_data or "{}")
        onboarding_data["keywords"] = keywords
        user.onboarding_data = json.dumps(onboarding_data)
        
        # Move to validation step
        user.onboarding_state = "validation"
        db.commit()
        
        # Update preferences in database
        await self._update_user_preferences(db, user)
        
        keywords_text = ", ".join(keywords)
        validation_message = f"""*Centres d'intérêt identifiés :*
{keywords_text}

*Étape 2/3 : Validation*

Ces sujets vous conviennent-ils pour vos résumés quotidiens ?

Répondez "oui" pour continuer ou modifiez la liste directement."""
        
        await self.whatsapp_service.send_text_message(user.phone_number, validation_message)
    
    async def _handle_onboarding_validation(self, db: Session, user: User, text: str):
        """Handle keywords validation during onboarding"""
        text_lower = text.lower().strip()
        
        if text_lower in ['oui', 'yes', 'ok', 'correct', 'valide']:
            # Proceed to schedule
            user.onboarding_state = "schedule"
            db.commit()
            
            schedule_message = """*Étape 3/3 : Horaire de livraison*

À quelle heure souhaitez-vous recevoir un résumé quotidien de vos sujets préférés ?

Exemples :
• "9h" ou "09:00" pour 9h du matin
• "18h30" pour 18h30
• "jamais" si vous ne voulez pas de résumés automatiques"""
            
            await self.whatsapp_service.send_text_message(user.phone_number, schedule_message)
            
        elif text_lower in ['non', 'no', 'incorrect']:
            # Go back to keywords
            user.onboarding_state = "keywords"
            db.commit()
            
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "*Reprenons vos centres d'intérêt*\n\nQuels sujets vous intéressent ? (ex: tech, sport, crypto)"
            )
        else:
            # Treat as new keywords
            keywords = [k.strip() for k in text.split(",") if k.strip()]
            if keywords:
                onboarding_data = json.loads(user.onboarding_data or "{}")
                onboarding_data["keywords"] = keywords
                user.onboarding_data = json.dumps(onboarding_data)
                user.onboarding_state = "validation"  # Re-validate new keywords
                db.commit()
                
                # Update preferences in database
                await self._update_user_preferences(db, user)
                
                keywords_text = ", ".join(keywords)
                validation_message = f"""*Centres d'intérêt mis à jour :*
{keywords_text}

Ces nouveaux sujets vous conviennent-ils ?

Répondez "oui" pour continuer ou modifiez-les à nouveau."""
                
                await self.whatsapp_service.send_text_message(user.phone_number, validation_message)
            else:
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "Répondez par 'oui', 'non' ou donnez de nouveaux centres d'intérêt."
                )
    
    async def _handle_onboarding_schedule(self, db: Session, user: User, text: str):
        """Handle schedule selection during onboarding"""
        text_lower = text.lower().strip()
        
        if text_lower in ['jamais', 'non', 'rien', 'skip']:
            schedule_time = None
        else:
            # Parse time
            schedule_time = self._parse_time_input(text)
            if not schedule_time:
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    "❌ Format d'heure non reconnu. Essayez : '9h', '09:00', '18h30' ou 'jamais'"
                )
                return
        
        # Store schedule
        onboarding_data = json.loads(user.onboarding_data or "{}")
        onboarding_data["schedule"] = schedule_time
        user.onboarding_data = json.dumps(onboarding_data)
        user.onboarding_state = "voice"
        db.commit()
        
        # Update preferences in database
        await self._update_user_preferences(db, user)
        
        if schedule_time:
            voice_message = f"""*Résumé quotidien programmé à {schedule_time}*

*Étape 3/3 : Finalisation*

Configuration terminée ! Vos résumés audio utiliseront la voix par défaut de Noto.

Le clonage vocal sera disponible dans une prochaine version.

Tapez "OK" pour finaliser votre configuration."""
        else:
            voice_message = """*Aucun résumé automatique configuré*

*Étape 3/3 : Finalisation*

Configuration terminée ! Vos résumés audio utiliseront la voix par défaut de Noto.

Le clonage vocal sera disponible dans une prochaine version.

Tapez "OK" pour finaliser votre configuration."""
        
        await self.whatsapp_service.send_text_message(user.phone_number, voice_message)
    
    async def _handle_onboarding_voice(self, db: Session, user: User, text: str):
        """Handle voice setup during onboarding - simplified without cloning"""
        if text.lower().strip() in ['ok', 'oui', 'yes', 'confirmer', 'valider', 'passer', 'skip']:
            # Move to final validation
            user.onboarding_state = "final_validation"
            db.commit()
            await self._show_final_validation(db, user)
        else:
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "Tapez 'OK' pour finaliser votre configuration Noto."
            )
    
    async def _handle_onboarding_final_validation(self, db: Session, user: User, text: str):
        """Handle final validation of all settings"""
        text_lower = text.lower().strip()
        
        if text_lower in ['1', 'centres', 'sujets', 'mots-clés', 'keywords']:
            # Go back to keywords
            user.onboarding_state = "keywords"
            db.commit()
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "*Modification des centres d'intérêt*\n\nQuels sujets souhaitez-vous suivre ?"
            )
        elif text_lower in ['2', 'horaire', 'schedule', 'heure']:
            # Go back to schedule  
            user.onboarding_state = "schedule"
            db.commit()
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "*Modification de l'horaire*\n\nÀ quelle heure souhaitez-vous recevoir vos résumés quotidiens ?"
            )
        elif text_lower in ['3', 'voix', 'voice', 'audio']:
            # Go back to voice
            user.onboarding_state = "voice"
            db.commit()
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "*Configuration de voix*\n\nEnvoyez un audio de 10-15 secondes ou tapez 'passer'"
            )
        elif text_lower in ['ok', 'oui', 'yes', 'confirmer', 'valider']:
            # Finalize onboarding
            user.onboarding_state = "final"
            db.commit()
            await self._finalize_onboarding(db, user)
        else:
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "Tapez le numéro de l'élément à modifier (1, 2, 3) ou 'OK' pour confirmer."
            )
    
    async def _show_final_validation(self, db: Session, user: User):
        """Show final validation summary"""
        onboarding_data = json.loads(user.onboarding_data or "{}")
        keywords = onboarding_data.get("keywords", [])
        schedule_time = onboarding_data.get("schedule")
        
        # Check voice profile
        voice_profiles = db.query(VoiceProfile).filter(VoiceProfile.user_id == user.id).count()
        
        keywords_text = ", ".join(keywords) if keywords else "Aucun défini"
        schedule_text = schedule_time if schedule_time else "Aucun résumé automatique"
        voice_text = "Voix personnalisée" if voice_profiles > 0 else "Voix par défaut"
        
        validation_message = f"""*Configuration Noto*

*1. Centres d'intérêt :* {keywords_text}

*2. Résumé quotidien :* {schedule_text}

*3. Voix :* {voice_text}

Tapez le numéro pour modifier un paramètre ou 'OK' pour confirmer et commencer."""
        
        await self.whatsapp_service.send_text_message(user.phone_number, validation_message)
    
    async def _handle_onboarding_final(self, db: Session, user: User, text: str):
        """Handle final onboarding step"""
        await self._complete_onboarding(db, user)
    
    async def _update_user_preferences(self, db: Session, user: User):
        """Update user preferences from onboarding data"""
        onboarding_data = json.loads(user.onboarding_data or "{}")
        keywords = onboarding_data.get("keywords", ["actualités"])
        schedule_time = onboarding_data.get("schedule")
        
        # Update or create user preferences
        preference = db.query(Preference).filter(Preference.user_id == user.id).first()
        if not preference:
            preference = Preference(
                user_id=user.id,
                max_results=5,
                summary_style="concise"
            )
            db.add(preference)
        
        preference.keywords = json.dumps(keywords)
        preference.daily_schedule = schedule_time
        db.commit()
    
    async def _finalize_onboarding(self, db: Session, user: User):
        """Complete onboarding setup and generate first summary"""
        try:
            # Update user preferences first
            await self._update_user_preferences(db, user)
            
            # Get keywords for summary
            onboarding_data = json.loads(user.onboarding_data or "{}")
            keywords = onboarding_data.get("keywords", ["actualités"])
            
            # Complete onboarding
            user.onboarding_state = "completed"
            user.is_onboarded = True
            db.commit()
            
            completion_message = """*Configuration terminée*

Noto est maintenant prêt. Voici un premier résumé d'actualité pour tester le tout :"""
            
            await self.whatsapp_service.send_text_message(user.phone_number, completion_message)
            
            # Generate first summary with NEW pipeline
            await self.generate_daily_brief(db, user, None)  # Use user's keywords from onboarding
            
            # Send final instructions
            final_message = """*Tout fonctionne parfaitement*

*Utilisation :*
• Posez n'importe quelle question
• Je recherche et résume pour vous
• Réponse en texte + audio

*Commandes utiles :*
• /pref - Modifier vos préférences
• /help - Aide complète
• /stop - Se désabonner des résumés

*Prêt à répondre à vos questions*"""
            
            await self.whatsapp_service.send_text_message(user.phone_number, final_message)
            
        except Exception as e:
            logger.error(f"Error finalizing onboarding: {e}")
            await self._complete_onboarding(db, user)
    
    async def _complete_onboarding(self, db: Session, user: User):
        """Emergency completion of onboarding"""
        user.onboarding_state = "completed"
        user.is_onboarded = True
        db.commit()
        
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            """✅ Configuration terminée !

Votre assistant est prêt. Posez-moi n'importe quelle question !

Tapez /help pour voir toutes les fonctionnalités."""
        )
    
    def _parse_time_input(self, time_str: str) -> Optional[str]:
        """Parse time input and return HH:MM format"""
        time_str = time_str.strip().lower()
        
        # Handle common formats
        patterns = [
            (r'^(\d{1,2})h(\d{2})?$', lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"),
            (r'^(\d{1,2}):(\d{2})$', lambda m: f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"),
            (r'^(\d{1,2})$', lambda m: f"{int(m.group(1)):02d}:00"),
        ]
        
        for pattern, formatter in patterns:
            match = re.match(pattern, time_str)
            if match:
                try:
                    formatted_time = formatter(match)
                    # Validate time
                    hour, minute = map(int, formatted_time.split(':'))
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        return formatted_time
                except:
                    continue
        
        return None
    
    # Command handlers
    async def _handle_start_command(self, db: Session, user: User, text: str):
        """Handle /start command"""
        welcome_message = f"""👋 Salut {user.name} !

🤖 Je suis votre assistant Perplexity personnel.

✨ **Fonctionnalités :**
📊 Recherche web temps réel  
🎙️ Réponses audio avec votre voix
📰 Actualités personnalisées
🔍 Analyse intelligente des sources

💬 **Utilisation :**
Posez simplement vos questions en français !

⚙️ **Configuration :**
/voice - Cloner votre voix
/keywords - Centres d'intérêt  
/help - Aide complète

Que voulez-vous savoir ?"""
        
        await self.whatsapp_service.send_text_message(user.phone_number, welcome_message)
    
    async def _handle_help_command(self, db: Session, user: User, text: str):
        """Handle /help command"""
        help_message = """📖 **Aide Perplexity WhatsApp**

🔍 **Recherche :**
- Posez n'importe quelle question
- "Actualités tech aujourd'hui"
- "Cours Bitcoin maintenant"  
- "Météo Paris demain"

🎙️ **Audio personnalisé :**
/voice - Envoyez 10s d'audio pour cloner votre voix

⚙️ **Configuration :**
/keywords tech,crypto,sport - Vos centres d'intérêt
/schedule 09:00 - Résumé quotidien
/stats - Vos statistiques
/clear - Effacer l'historique

💡 **Conseils :**
- Questions précises = meilleures réponses
- Sources automatiquement citées [1][2][3]
- Audio généré avec votre voix clonée

❓ Des questions ? Demandez-moi !"""
        
        await self.whatsapp_service.send_text_message(user.phone_number, help_message)
    
    async def _handle_voice_command(self, db: Session, user: User, text: str):
        """Handle /voice command"""
        voice_message = """🎙️ **Clonage de voix**

Pour personnaliser ma voix avec la vôtre :

1️⃣ Enregistrez un audio de **10-15 secondes**
2️⃣ Parlez clairement en français
3️⃣ Environnement calme (sans bruit de fond)
4️⃣ Envoyez-moi cet audio

✅ **Conseils pour un bon clonage :**
- Parlez naturellement, ni trop vite ni trop lent
- Évitez les "euh", pauses longues
- Une phrase complète fonctionne bien

🔄 Vous pouvez refaire le clonage à tout moment en renvoyant un nouvel audio.

Prêt ? Envoyez votre audio !"""
        
        await self.whatsapp_service.send_text_message(user.phone_number, voice_message)
    
    async def _handle_keywords_command(self, db: Session, user: User, text: str):
        """Handle /keywords command"""
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                """🏷️ **Centres d'intérêt**

Définissez vos sujets préférés pour des résultats plus pertinents.

**Format :** /keywords tech,crypto,sport,santé

**Exemples :**
- /keywords intelligence artificielle,startups
- /keywords football,NBA,tennis
- /keywords blockchain,DeFi,NFT

**Mots-clés actuels :** Aucun défini

Tapez /keywords suivi de vos centres d'intérêt !"""
            )
            return
        
        keywords_str = parts[1]
        keywords = [k.strip() for k in keywords_str.split(",")]
        
        # Update or create preferences
        preference = db.query(Preference).filter(Preference.user_id == user.id).first()
        if not preference:
            preference = Preference(user_id=user.id)
            db.add(preference)
        
        preference.keywords = json.dumps(keywords)
        db.commit()
        
        keywords_list = "\n".join([f"• {kw}" for kw in keywords])
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            f"""✅ **Centres d'intérêt mis à jour !**

Vos mots-clés :
{keywords_list}

Ces sujets seront priorisés dans vos recherches."""
        )
    
    async def _handle_schedule_command(self, db: Session, user: User, text: str):
        """Handle /schedule command"""
        # TODO: Implement scheduled summaries
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            "⏰ Résumés programmés - Fonctionnalité en développement !"
        )
    
    async def _handle_stats_command(self, db: Session, user: User, text: str):
        """Handle /stats command"""
        # Get user statistics
        conversation_count = db.query(Conversation).filter(Conversation.user_id == user.id).count()
        
        total_tokens = db.query(Conversation).filter(
            Conversation.user_id == user.id
        ).with_entities(Conversation.tokens_used).all()
        
        total_tokens_used = sum([t[0] or 0 for t in total_tokens])
        
        voice_profiles = db.query(VoiceProfile).filter(VoiceProfile.user_id == user.id).count()
        
        stats_message = f"""📊 **Vos statistiques**

👤 **Profil :**
- Nom : {user.name}
- Langue : {user.language}
- Inscrit le : {user.created_at.strftime('%d/%m/%Y')}

💬 **Utilisation :**
- Conversations : {conversation_count}
- Tokens utilisés : {total_tokens_used:,}
- Profils vocaux : {voice_profiles}

🎙️ **Audio :** {'Activé' if voice_profiles > 0 else 'Non configuré'}

⚙️ Tapez /help pour plus d'options !"""
        
        await self.whatsapp_service.send_text_message(user.phone_number, stats_message)
    
    async def _handle_clear_command(self, db: Session, user: User, text: str):
        """Handle /clear command"""
        # Delete user's conversation history
        db.query(Conversation).filter(Conversation.user_id == user.id).delete()
        db.commit()
        
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            "✅ Historique des conversations effacé !"
        )
    
    async def _handle_pref_command(self, db: Session, user: User, text: str):
        """Handle /pref command to modify preferences"""
        preference = db.query(Preference).filter(Preference.user_id == user.id).first()
        keywords = json.loads(preference.keywords) if preference and preference.keywords else []
        schedule = preference.daily_schedule if preference else "Non configuré"
        voice_profiles = db.query(VoiceProfile).filter(VoiceProfile.user_id == user.id).count()
        
        pref_message = f"""⚙️ **Vos préférences actuelles**

📌 **Centres d'intérêt :**
{', '.join(keywords) if keywords else 'Aucun défini'}

⏰ **Résumé quotidien :**
{schedule if schedule else 'Désactivé'}

🎙️ **Voix personnalisée :**
{'Configurée' if voice_profiles > 0 else 'Non configurée'}

**Pour modifier :**
• /keywords [sujets] - Changer vos centres d'intérêt
• /schedule [heure] - Programmer résumés (ex: /schedule 9h)
• /voice - Reconfigurer votre voix
• /stop - Désactiver résumés automatiques"""
        
        await self.whatsapp_service.send_text_message(user.phone_number, pref_message)
    
    async def _handle_stop_command(self, db: Session, user: User, text: str):
        """Handle /stop command to unsubscribe from scheduled summaries"""
        preference = db.query(Preference).filter(Preference.user_id == user.id).first()
        
        if preference:
            preference.daily_schedule = None
            db.commit()
            
            stop_message = """🔕 **Résumés automatiques désactivés**

Vous ne recevrez plus de résumés quotidiens automatiques.

**Pour réactiver :**
• /schedule [heure] - Ex: /schedule 9h
• /pref - Voir toutes vos préférences

💬 Vous pouvez toujours me poser des questions à tout moment !"""
        else:
            stop_message = """ℹ️ **Aucun résumé automatique configuré**

Vous n'avez pas de résumés quotidiens programmés.

**Pour en configurer :**
• /schedule [heure] - Ex: /schedule 9h
• /pref - Voir vos préférences"""
        
        await self.whatsapp_service.send_text_message(user.phone_number, stop_message)
    
    async def health_check(self) -> Dict:
        """Check health of all services"""
        health_status = {
            "orchestrator": "healthy",
            "llm_service": await self.llm_service.health_check(),
            "tts_service": await self.tts_service.health_check(),
            "whatsapp_service": await self.whatsapp_service.health_check(),
            "perplexica_enabled": self.use_perplexica
        }
        
        # Add Perplexica health check if enabled
        if self.use_perplexica and self.perplexica_service:
            health_status["perplexica_service"] = await self.perplexica_service.health_check()
        
        return health_status
    
    async def generate_daily_brief(
        self,
        db: Session,
        user: User,
        topic: Optional[str] = None
    ):
        """Generate and send daily news brief"""
        try:
            # Get user preferences and onboarding data
            preferences = db.query(Preference).filter(Preference.user_id == user.id).first()
            onboarding_data = json.loads(user.onboarding_data or "{}")
            
            # Use provided topic or user's keywords from onboarding
            if not topic:
                # First check onboarding keywords (primary source)
                keywords = onboarding_data.get("keywords", [])
                # Fallback to preferences if available
                if not keywords and preferences:
                    keywords = json.loads(preferences.keywords or "[]")
                topic = " ".join(keywords) if keywords else "actualités France"
            elif not topic:
                topic = "actualités France"
            
            # PASS 1: Collect news
            logger.info(f"PASS 1: Collecting news for {topic}")
            news_result = await self.news_collector.collect_news(
                topic=topic,
                time_range="24h",
                limit=10,
                lang=user.language
            )
            
            # Check if we have enough news
            if len(news_result.get("items", [])) < MINIMUM_NEWS_ITEMS:
                await self.whatsapp_service.send_text_message(
                    user.phone_number,
                    f"Peu d'actualités trouvées pour '{topic}'. Réessayez plus tard."
                )
                return
            
            # PASS 2: Generate brief
            logger.info(f"PASS 2: Generating brief from {len(news_result['items'])} items")
            brief_result = await self.news_summarizer.brief_from_items(
                items=news_result["items"],
                first_name=user.name.split()[0] if user.name else "vous",
                max_words=NEWS_BRIEF_MAX_WORDS,
                audio_words=NEWS_BRIEF_AUDIO_WORDS,
                lang=user.language
            )
            
            # Send text brief (without emojis, professional tone)
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                brief_result["brief_text"]
            )
            
            # Generate and send audio if requested
            if preferences and getattr(preferences, "wants_audio", False):
                logger.info("Generating audio for brief")
                voice_profile = None
                if preferences.voice_profile_id:
                    voice_profile = db.query(VoiceProfile).filter(
                        VoiceProfile.id == preferences.voice_profile_id
                    ).first()
                
                audio_path = await self.tts_service.text_to_speech(
                    text=brief_result["tts_script"],
                    voice_profile_path=voice_profile.voice_file_path if voice_profile else None,
                    language=user.language
                )
                
                if audio_path:
                    await self.whatsapp_service.send_audio_message(
                        user.phone_number,
                        audio_path
                    )
            
            # Log delivery
            self._log_delivery(db, user, topic, brief_result)
            
        except Exception as e:
            logger.error(f"Error generating daily brief: {e}")
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "❌ Erreur lors de la génération du brief. Réessayez plus tard."
            )
    
    def _extract_topic_from_query(self, text: str) -> str:
        """Extract topic from news query"""
        # Remove temporal markers
        temporal_words = [
            "aujourd'hui", "hier", "dernières", "derniers",
            "actualités", "news", "depuis", "récentes"
        ]
        
        words = text.lower().split()
        filtered_words = [w for w in words if w not in temporal_words]
        
        if filtered_words:
            return " ".join(filtered_words)
        return "actualités France"
    
    def _log_delivery(self, db: Session, user: User, topic: str, brief_result: Dict):
        """Log brief delivery to database"""
        try:
            # This would require adding a Delivery model to database.py
            # For now, just log to conversation history
            conversation = Conversation(
                user_id=user.id,
                query=f"briefing: {topic}",
                response_text=brief_result["brief_text"],
                sources=json.dumps(brief_result.get("citations", [])),
                processing_time=0,
                tokens_used=0
            )
            db.add(conversation)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log delivery: {e}")
    
    async def _handle_briefing_command(self, db: Session, user: User, text: str):
        """Handle /briefing command"""
        parts = text.split(maxsplit=1)
        topic = parts[1] if len(parts) > 1 else None
        
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            "Génération de votre brief en cours..."
        )
        
        await self.generate_daily_brief(db, user, topic)
    
    async def _handle_centres_command(self, db: Session, user: User, text: str):
        """Handle /centres command to update topics"""
        parts = text.split(maxsplit=1)
        
        # Get current keywords from onboarding
        onboarding_data = json.loads(user.onboarding_data or "{}")
        current_keywords = onboarding_data.get("keywords", [])
        
        if len(parts) < 2:
            keywords_text = ", ".join(current_keywords) if current_keywords else "Aucun défini"
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                f"Utilisez : /centres tech,sport,économie\n\nVos centres actuels : {keywords_text}"
            )
            return
        
        topics = [t.strip() for t in parts[1].split(",")]
        
        # Update both onboarding data and preferences
        onboarding_data["keywords"] = topics
        user.onboarding_data = json.dumps(onboarding_data)
        
        preference = db.query(Preference).filter(Preference.user_id == user.id).first()
        if not preference:
            preference = Preference(user_id=user.id)
            db.add(preference)
        
        preference.keywords = json.dumps(topics)
        db.commit()
        
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            f"Centres d'intérêt mis à jour : {', '.join(topics)}"
        )
    
    async def _handle_frequence_command(self, db: Session, user: User, text: str):
        """Handle /frequence command"""
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            "Configuration de la fréquence\n\nExemples :\n/frequence quotidien 9h\n/frequence 2x_semaine\n/frequence jamais"
        )
    
    async def _handle_audio_command(self, db: Session, user: User, text: str):
        """Handle /audio command"""
        parts = text.split()
        
        if len(parts) < 2:
            await self.whatsapp_service.send_text_message(
                user.phone_number,
                "Utilisez : /audio on ou /audio off"
            )
            return
        
        # Update audio preference
        preference = db.query(Preference).filter(Preference.user_id == user.id).first()
        if not preference:
            preference = Preference(user_id=user.id)
            db.add(preference)
        
        # Store audio preference in onboarding data for now
        onboarding_data = json.loads(user.onboarding_data or "{}")
        audio_enabled = parts[1].lower() == "on"
        onboarding_data["wants_audio"] = audio_enabled
        user.onboarding_data = json.dumps(onboarding_data)
        
        await self.whatsapp_service.send_text_message(
            user.phone_number,
            f"Audio {'activé' if audio_enabled else 'désactivé'}"
        )
        
        db.commit()