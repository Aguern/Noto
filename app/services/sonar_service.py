"""Perplexity Sonar Service - Remplacement simple de Perplexica"""
import os
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

class SonarService:
    """Service Perplexity Sonar - Remplace toute la stack Perplexica"""
    
    def __init__(self):
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        self.base_url = "https://api.perplexity.ai"
        self.model = os.getenv("SONAR_MODEL", "sonar-reasoning")  # ou sonar-reasoning-pro
        self.timeout = 60.0  # Plus de timeouts Perplexica !
        
        if not self.api_key:
            logger.error("PERPLEXITY_API_KEY manquante dans .env")
            raise ValueError("Configuration Sonar manquante")
        
        logger.info(f"SonarService initialized with model: {self.model}")
    
    async def search_multi_interests(
        self,
        interests: List[str],
        base_query: str = "actualités",
        max_results_per_interest: int = 1  # Ignoré - Sonar gère tout
    ) -> Dict:
        """
        Remplace PerplexicaService.search_multi_interests()
        
        Simplicité extrême : 1 seul appel pour tout !
        """
        try:
            today = datetime.now().strftime("%d %B %Y")
            today_fr = datetime.now().strftime("%d %B %Y")
            
            # PROMPT UNIFIÉ pour tous les centres d'intérêt
            prompt = self._build_unified_prompt(interests, today_fr)
            
            # UN SEUL APPEL SONAR pour TOUT
            result = await self._call_sonar_api(prompt)
            
            if result:
                return {
                    "success": True,
                    "interests_covered": [{
                        "interest": "multi-interests",
                        "sources": [{"content": result}]  # Format compatible
                    }],
                    "all_sources": [{"content": result}],
                    "processing_time": 0,  # Sonar gère l'infrastructure
                    "timestamp": datetime.utcnow().isoformat(),
                }
            else:
                return {"success": False, "error": "Sonar API failed"}
                
        except Exception as e:
            logger.error(f"❌ SonarService error: {e}")
            return {"success": False, "error": str(e)}
    
    def _build_unified_prompt(self, interests: List[str], today: str) -> str:
        """Construit le prompt unique pour tous les centres d'intérêt"""
        
        interests_str = ", ".join(interests)
        
        return f"""Tu es un assistant de veille actualité français expert.

MISSION : Génère un résumé factuel des actualités récentes (72h) pour ces centres d'intérêt : {interests_str}

CRITÈRES OBLIGATOIRES :
1. Actualités récentes (dernières 72h maximum)
2. Citations intégrées dans les phrases selon Le Monde, Figaro, etc.
3. Aucune hallucination - faits sourcés uniquement
4. Format structuré français professionnel

FORMAT OBLIGATOIRE :
## Résumé actualités récentes

### POLITIQUE
- Fait politique selon Le Monde et Figaro avec détails
- Autre développement selon France Info

### ÉCONOMIE  
- Indicateur économique selon Les Échos avec chiffres
- Autre actualité selon Reuters France

### [Autres centres selon la liste]

### SYNTHÈSE
- 2-3 points saillants selon l'ensemble des sources

STYLE : Citations naturelles intégrées (selon X, d'après Y, rapporte Z)."""

    async def _call_sonar_api(self, prompt: str) -> Optional[str]:
        """Appel unique à l'API Sonar"""
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system", 
                    "content": "Tu es un assistant de veille actualité français. Réponds uniquement avec des informations vérifiées et citées."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,  # Factuel
            "max_tokens": 3000,
            "search_domain_filter": [
                "lemonde.fr", "lefigaro.fr", "liberation.fr", 
                "franceinfo.fr", "bfmtv.com", "reuters.com",
                "afp.com", "20minutes.fr", "lci.fr"
            ],
            "search_recency_filter": "day",  # Actualités du jour
            "return_citations": True,
            "return_images": False
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PerplexityWhatsApp/1.0"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"🔍 Sonar {self.model} search starting...")
                
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.is_success:
                    result = response.json()
                    
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        logger.success(f"✅ Sonar completed: {len(content)} chars")
                        return content
                    else:
                        logger.error("❌ Sonar: Invalid response format")
                        return None
                        
                else:
                    error_text = response.text
                    logger.error(f"❌ Sonar API error: {response.status_code} - {error_text}")
                    
                    # Fallback gracieux si quota dépassé
                    if response.status_code == 429:
                        logger.warning("⚠️ Sonar rate limit - implementing backoff")
                        await asyncio.sleep(5)
                        return None
                    
                    return None
                    
        except httpx.TimeoutException:
            logger.error("❌ Sonar timeout (60s) - API surchargé")
            return None
        except Exception as e:
            logger.error(f"❌ Sonar exception: {e}")
            return None
    
    def format_for_whatsapp(
        self, 
        sonar_result: Dict, 
        user_name: str, 
        user_interests: List[str]
    ) -> Dict:
        """
        Format compatible avec le système WhatsApp existant
        """
        if not sonar_result.get("success"):
            return {
                "summary": f"Bonjour {user_name}, aucune actualité trouvée aujourd'hui.",
                "has_content": False
            }
        
        # Récupère le résumé Sonar
        content = sonar_result["all_sources"][0]["content"]
        
        # Formatage WhatsApp
        formatted = f"📰 *Résumé Noto* - {datetime.now().strftime('%d %B %Y')}\n\n"
        formatted += f"Bonjour {user_name},\n\n"
        formatted += content
        formatted += f"\n\n🤖 *Généré par Sonar AI*"
        
        return {
            "summary": formatted,
            "has_content": len(content) > 100,
            "source_count": content.count("["),  # Approximation du nombre de sources
            "interests_covered": len(user_interests)
        }
    
    async def health_check(self) -> Dict:
        """Check de santé Sonar"""
        try:
            # Test simple avec timeout court
            test_result = await asyncio.wait_for(
                self._call_sonar_api("Test de connectivité Sonar API"),
                timeout=10.0
            )
            
            return {
                "status": "healthy" if test_result else "degraded",
                "model": self.model,
                "api_url": self.base_url
            }
        except:
            return {"status": "unhealthy", "model": self.model}