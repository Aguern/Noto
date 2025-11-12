"""Prompt templates for news collection and summarization"""

# PASS 1 - Collection prompt template
COLLECTION_PROMPT_TEMPLATE = """Rôle : Assistant de veille. Pour « {topic} », dresse une SHORTLIST d'articles récents.
Privilégie {time_window} ; si la couverture est faible, étends à 72 h.

Sortie STRICTE (pas de prose) :
{{ "items": [ {{ "source":"...", "title":"...", "url":"https://...", "published_at_ISO":"YYYY-MM-DDTHH:MM:SSZ" }} ] }}

Règles : 6–10 items, sources distinctes si possible, exclure tout article sans date ou > 72 h.
Langue : {lang}
Topic : {topic}"""

# PASS 2 - Summary prompt template  
SUMMARY_PROMPT_TEMPLATE = """Génère un brief d'actualité pour {first_name}.

SOURCES DISPONIBLES :
{items}

RÈGLES STRICTES :
- Utilise UNIQUEMENT les items fournis (aucune autre source)
- Cite dans le texte : "selon X", "d'après Y"
- Deux à trois angles concrets max (événement, décision, chiffre)
- Style : oral professionnel, phrases courtes, zéro markdown
- AUCUN EMOJI dans le texte
- brief_text : ≤ {max_words} mots
- tts_script : {audio_words} mots (nombres en toutes lettres, dates lisibles)
- citations : uniquement les sources utilisées
- Commence par : "Bonjour {first_name}, voici les actualités du [date en français]."

SORTIE JSON STRICTE :
{{
  "brief_text": "... (≤ {max_words} mots, style oral, citations dans le texte) ...",
  "tts_script": "... (90–140 mots, nombres en toutes lettres, dates lisibles) ...",
  "citations": [
    {{"source":"...", "title":"...", "url":"...", "published_at_ISO":"YYYY-MM-DDTHH:MM:SSZ"}}
  ]
}}

Langue : {lang}"""

# Daily brief greeting templates by time of day (sans emojis)
GREETINGS = {
    "morning": {
        "fr": "Bonjour {first_name}, voici les actualités du matin",
        "en": "Good morning {first_name}, here's your morning briefing"
    },
    "afternoon": {
        "fr": "Bonjour {first_name}, voici les actualités de l'après-midi",
        "en": "Good afternoon {first_name}, here's your afternoon briefing"
    },
    "evening": {
        "fr": "Bonsoir {first_name}, voici les actualités du soir",
        "en": "Good evening {first_name}, here's your evening briefing"
    }
}

# Closing templates
CLOSINGS = {
    "morning": {
        "fr": "Bonne journée !",
        "en": "Have a great day!"
    },
    "afternoon": {
        "fr": "Bon après-midi !",
        "en": "Have a good afternoon!"
    },
    "evening": {
        "fr": "Bonne soirée !",
        "en": "Have a good evening!"
    }
}