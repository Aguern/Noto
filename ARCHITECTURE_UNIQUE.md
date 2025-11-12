# 🎯 Architecture Unique - Pipeline Perplexica Optimisé

## Objectif
Un seul point d'entrée : **Perplexica** → Informations complètes → **LLM** → Synthèse Audio

## Flux Simplifié

```
User Keywords → Perplexica Multi-Interest Search → Enhanced Extraction → LLM Summary → TTS Audio
     ↓                    ↓                           ↓                    ↓           ↓
  [sport, tech]    [5 requêtes parallèles]    [8000+ chars/source]   [Synthèse]   [Audio]
```

## Suppression des Doublons

### ❌ À SUPPRIMER :
- `SearchService` traditionnel (sauf pour health checks)
- Pipeline alternatif dans `Orchestrator._process_search_query()`
- `LLMService.summarize_for_whatsapp()` (redondant avec Perplexica formatting)

### ✅ À CONSERVER :
- `PerplexicaService` comme source unique
- `AdvancedContentExtractor` intégré dans Perplexica
- `SmartSourceManager` pour filtrage
- `KeyFactsExtractor` pour NER

## Architecture Cible

1. **Perplexica Enhanced** :
   - Multi-interest queries
   - Advanced content extraction (8000+ chars)
   - Smart source filtering
   - NER + key facts extraction

2. **Direct LLM Processing** :
   - Perplexica fournit le contenu riche directement
   - Plus de pipeline parallèle
   - Format Noto personnalisé

3. **TTS Output** :
   - Synthèse audio unique
   - Sources citées séparément

## Bénéfices
- **0% Hallucinations** : Contenu riche = pas d'invention
- **100% Cohérence** : Un seul pipeline
- **Maximum d'Information** : 8000+ chars vs 200 chars actuels
- **Killer Feature** : Actualités factuelles, sourcées, vraies