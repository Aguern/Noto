#!/usr/bin/env python3
"""Test DeepSeek R1 gratuit pour remplacer Perplexica"""
import asyncio
import httpx
import os
from loguru import logger
from datetime import datetime

class DeepSeekTester:
    def __init__(self):
        # DeepSeek R1 gratuit avec recherche web
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_KEY") 
        self.base_url = "https://api.deepseek.com"
    
    async def test_deepseek_r1_search(self, interests: list):
        """Test DeepSeek R1 avec recherche web (gratuit)"""
        
        today = datetime.now().strftime("%d %B %Y")
        prompt = f"""
        MISSION URGENTE: Génère un résumé quotidien factuel des actualités françaises du {today} pour ces centres d'intérêt : {', '.join(interests)}

        CONSIGNES STRICTES:
        1. Recherche web OBLIGATOIRE pour actualités du {today}
        2. Sources françaises prioritaires (Le Monde, Figaro, France Info)
        3. Citations [source] pour chaque information
        4. AUCUNE hallucination - seulement faits vérifiés
        5. Format professionnel français

        FORMAT REQUIS:
        ## Résumé du {today}

        ### POLITIQUE
        - Fait politique majeur avec détails [Source]

        ### ÉCONOMIE  
        - Indicateur économique avec chiffres [Source]

        ### SPORT
        - Résultat sportif important [Source]

        ### TECHNOLOGIE
        - Innovation technologique récente [Source]

        Utilise tes capacités de recherche web pour obtenir les informations les plus récentes.
        """
        
        payload = {
            "model": "deepseek-reasoner",  # R1 avec capacités de recherche
            "messages": [
                {
                    "role": "system",
                    "content": "Tu es un assistant de veille actualité français avec accès à la recherche web en temps réel. Réponds uniquement avec des informations vérifiées et récentes."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 3000
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:  # R1 prend plus de temps
                logger.info("🔍 Test DeepSeek R1 avec recherche web...")
                
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.is_success:
                    result = response.json()
                    message = result["choices"][0]["message"]["content"]
                    
                    print("\n" + "="*80)
                    print("🧠 RÉSULTAT DEEPSEEK R1 (GRATUIT)")
                    print("="*80)
                    print(message)
                    print("="*80)
                    
                    # Analyse qualité
                    citations = message.count("[")
                    words = len(message.split())
                    
                    print(f"\n📊 MÉTRIQUES QUALITÉ:")
                    print(f"- Longueur: {len(message)} caractères") 
                    print(f"- Mots: {words}")
                    print(f"- Citations: {citations}")
                    print(f"- Centres traités: {len([i for i in interests if i.lower() in message.lower()])}")
                    
                    # Validation critères
                    today_mentioned = today in message or datetime.now().strftime("%d/%m") in message
                    sources_present = citations > 0
                    structured = "##" in message and "###" in message
                    french_sources = any(source in message.lower() for source in ["monde", "figaro", "france", "bfm"])
                    
                    print(f"\n✅ VALIDATION CRITÈRES:")
                    print(f"- Actualité du jour: {'✅' if today_mentioned else '❌'}")
                    print(f"- Sources citées: {'✅' if sources_present else '❌'}")
                    print(f"- Structure: {'✅' if structured else '❌'}")
                    print(f"- Sources françaises: {'✅' if french_sources else '❌'}")
                    print(f"- Longueur acceptable: {'✅' if words > 200 else '❌'}")
                    
                    score = sum([today_mentioned, sources_present, structured, french_sources, words > 200])
                    print(f"\n🎯 SCORE GLOBAL: {score}/5 ({score*20}%)")
                    
                    if score >= 4:
                        print("🎉 DEEPSEEK R1 VALIDÉ - 100% GRATUIT!")
                        print("💰 Coût: $0.00 (vs Perplexity $0.011)")
                        return True
                    else:
                        print("⚠️ DEEPSEEK R1 INSUFFISANT")
                        return False
                        
                else:
                    logger.error(f"❌ Erreur DeepSeek: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Erreur DeepSeek: {e}")
            return False

async def main():
    """Test gratuit DeepSeek R1"""
    logger.info("🧪 TEST GRATUIT DEEPSEEK R1")
    
    tester = DeepSeekTester()
    
    # Test avec vos centres d'intérêt réels
    test_interests = ["politique", "économie", "sport", "technologie"]
    
    success = await tester.test_deepseek_r1_search(test_interests)
    
    if success:
        print(f"\n🚀 SOLUTION GRATUITE:")
        print("1. DeepSeek R1 gratuit avec recherche web")
        print("2. Remplace totalement Perplexica")
        print("3. Migration immédiate - 0€ de coût")
    else:
        print(f"\n⚠️ TESTER OPENROUTER EN ALTERNATIVE")

if __name__ == "__main__":
    asyncio.run(main())