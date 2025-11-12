"""Scheduler service for automated summaries"""
import asyncio
import json
from datetime import datetime, time, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from loguru import logger
import threading
import time as time_module

from app.models.database import User, Preference, get_db
from app.services.orchestrator import MessageOrchestrator


class SchedulerService:
    """Service for handling scheduled summary delivery"""
    
    def __init__(self):
        self.orchestrator = None  # Will be set later to avoid circular import
        self.is_running = False
        self.scheduler_thread = None
    
    def set_orchestrator(self, orchestrator: MessageOrchestrator):
        """Set orchestrator instance (called after initialization)"""
        self.orchestrator = orchestrator
    
    def start_scheduler(self):
        """Start the scheduler in a background thread"""
        if self.is_running:
            return
        
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        logger.info("Scheduler service started")
    
    def stop_scheduler(self):
        """Stop the scheduler"""
        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("Scheduler service stopped")
    
    def _run_scheduler(self):
        """Run the scheduler loop"""        
        while self.is_running:
            try:
                # Check every minute for scheduled summaries
                asyncio.run(self._check_and_send_summaries())
                time_module.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time_module.sleep(60)
    
    async def _check_and_send_summaries(self):
        """Check if any users need summaries sent now"""
        try:
            current_time = datetime.now().time()
            current_hour_minute = f"{current_time.hour:02d}:{current_time.minute:02d}"
            
            db = next(get_db())
            
            # Find users who should receive summaries now
            users_for_summary = db.query(User).join(Preference).filter(
                Preference.daily_schedule == current_hour_minute,
                User.is_active == True,
                User.is_onboarded == True
            ).all()
            
            if users_for_summary:
                logger.info(f"Found {len(users_for_summary)} users for scheduled summary at {current_hour_minute}")
                
                # Send summaries
                await self._send_scheduled_summaries(users_for_summary)
            
            db.close()
            
        except Exception as e:
            logger.error(f"Error checking scheduled summaries: {e}")
    
    async def _send_scheduled_summaries(self, users: List[User]):
        """Send scheduled summaries to users"""
        if not self.orchestrator:
            logger.error("Orchestrator not set for scheduler service")
            return
        
        for user in users:
            try:
                await self._send_user_summary(user)
            except Exception as e:
                logger.error(f"Error sending summary to {user.phone_number}: {e}")
    
    async def _send_user_summary(self, user: User):
        """Send personalized summary to a user"""
        try:
            db = next(get_db())
            
            # Get user preferences
            preference = db.query(Preference).filter(Preference.user_id == user.id).first()
            if not preference:
                db.close()
                return
            
            keywords = json.loads(preference.keywords) if preference.keywords else ["actualités"]
            
            # Create query based on user's interests
            query = f"dernières actualités {' '.join(keywords[:3])} aujourd'hui"  # Limit to 3 keywords
            
            # Send greeting message
            greeting_time = self._get_time_greeting()
            greeting_message = f"""🌅 **{greeting_time} !**

Voici votre résumé quotidien personnalisé sur : {', '.join(keywords)}"""
            
            await self.orchestrator.whatsapp_service.send_text_message(
                user.phone_number, 
                greeting_message
            )
            
            # Process the search query (this will generate and send the summary)
            start_time = datetime.utcnow()
            await self.orchestrator._process_search_query(db, user, query, start_time)
            
            # Send sources reminder
            sources_message = """📚 **Sources citées dans le résumé :**
Les références [1], [2], [3]... correspondent aux liens des sources utilisées.

⚙️ Pour modifier vos préférences : /pref
🔕 Pour désactiver ces résumés : /stop"""
            
            await self.orchestrator.whatsapp_service.send_text_message(
                user.phone_number,
                sources_message
            )
            
            logger.info(f"Sent scheduled summary to {user.phone_number}")
            db.close()
            
        except Exception as e:
            logger.error(f"Error sending summary to user {user.phone_number}: {e}")
    
    def _get_time_greeting(self) -> str:
        """Get appropriate greeting based on time"""
        current_hour = datetime.now().hour
        
        if 5 <= current_hour < 12:
            return "Bonjour"
        elif 12 <= current_hour < 18:
            return "Bon après-midi"
        elif 18 <= current_hour < 22:
            return "Bonsoir"
        else:
            return "Bonne nuit"
    
    def get_active_schedules(self) -> Dict:
        """Get information about active scheduled summaries"""
        try:
            db = next(get_db())
            
            scheduled_users = db.query(User).join(Preference).filter(
                Preference.daily_schedule.isnot(None),
                User.is_active == True,
                User.is_onboarded == True
            ).all()
            
            schedules = {}
            for user in scheduled_users:
                schedule_time = user.preferences.daily_schedule
                if schedule_time not in schedules:
                    schedules[schedule_time] = 0
                schedules[schedule_time] += 1
            
            db.close()
            
            return {
                "total_scheduled_users": len(scheduled_users),
                "schedules_by_time": schedules,
                "scheduler_running": self.is_running
            }
            
        except Exception as e:
            logger.error(f"Error getting schedule info: {e}")
            return {"error": str(e)}


# Global scheduler instance
scheduler_service = SchedulerService()