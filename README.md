# 🤖 Perplexity WhatsApp Bot

> AI-powered WhatsApp bot with real-time web search, natural voice synthesis, and intelligent responses

## 🎯 Features

- **🔍 Real-time Web Search** - Powered by SearxNG
- **🧠 Intelligent Summaries** - Using Groq (Llama 3.8B) - FREE tier
- **🎙️ Natural Voice Synthesis** - XTTS-v2 with voice cloning
- **📱 WhatsApp Integration** - Business API with webhooks
- **🗃️ User Management** - Preferences, history, voice profiles
- **⚡ Performance** - Redis caching, async processing
- **🐳 Containerized** - Docker deployment ready

## 🏗️ Architecture

```
WhatsApp User → Webhook → Orchestrator
                              ↓
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
   Search Engine         LLM Engine           TTS Engine
   (SearxNG)             (Groq Free)          (XTTS-v2)
        ↓                     ↓                     ↓
        └─────────────────────┼─────────────────────┘
                              ↓
                       SQLite Database
                    (users, voices, cache)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- WhatsApp Business API account
- Groq API key (free)

### 1. Clone and Setup

```bash
git clone <your-repo>
cd perplexity-whatsapp

# Create conda environment for XTTS-v2 (recommended for Apple Silicon)
conda create -n perplexity-bot python=3.10
conda activate perplexity-bot
conda install pytorch torchvision -c pytorch

# Install dependencies
pip install -r requirements.txt
pip install TTS  # For XTTS-v2
```

### 2. Configuration

Edit `.env` file with your API keys:

```bash
# WhatsApp Business API
WHATSAPP_TOKEN=YOUR_RENEWED_TOKEN_HERE
WHATSAPP_PHONE_NUMBER_ID=692914853905742
WHATSAPP_VERIFY_TOKEN=1a76d9073144451f694ed6b2d24a9eba

# Groq API (FREE)
GROQ_API_KEY=your_groq_api_key_here

# Other settings (defaults should work)
SEARXNG_URL=http://localhost:4000
REDIS_URL=redis://localhost:6379
TTS_DEVICE=mps  # For Apple Silicon, cpu for others
```

### 3. Start Services

```bash
# Start Redis and SearxNG
docker-compose up -d

# Initialize database
python -c "from app.models.database import init_db; init_db()"

# Test the pipeline
python test_pipeline.py
```

### 4. Run the Bot

```bash
# Development
python app/api/main.py

# Production
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

### 5. Setup WhatsApp Webhook

In your Meta Developer Console, set webhook URL to:
```
https://your-domain.com/webhook
```

Or use ngrok for local testing:
```bash
ngrok http 8000
# Use the https URL provided by ngrok
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
python test_pipeline.py
```

This will test:
- ✅ Database connectivity
- ✅ SearxNG search service  
- ✅ Groq LLM integration
- ✅ XTTS-v2 voice synthesis
- ✅ WhatsApp API connectivity
- ✅ Complete pipeline integration

### Manual Testing

Use the provided test endpoints:

```bash
# Test search
curl -X POST http://localhost:8000/test/search \
  -H "Content-Type: application/json" \
  -d '{"query": "latest AI news"}'

# Test LLM
curl -X POST http://localhost:8000/test/llm \
  -H "Content-Type: application/json" \
  -d '{"query": "summarize AI trends"}'

# Test TTS
curl -X POST http://localhost:8000/test/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test"}'

# Test complete message processing
curl -X POST http://localhost:8000/test/message \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890", "text": "latest tech news"}'
```

## 💬 Usage

### User Commands

Once your bot is running, users can interact via WhatsApp:

**Basic Usage:**
```
User: "Latest AI news today"
Bot: [Searches web, generates summary with sources, sends text + audio]
```

**Commands:**
- `/start` - Welcome message and setup
- `/voice` - Clone your voice (send 10s audio sample)
- `/keywords tech,AI,crypto` - Set your interests
- `/help` - Full help guide
- `/stats` - Your usage statistics
- `/clear` - Clear conversation history

### Voice Cloning

1. Send `/voice` command
2. Record and send 10-15 seconds of clear audio
3. Bot clones your voice
4. All future responses will use your cloned voice

## 🛠️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key (free tier) | Required |
| `WHATSAPP_TOKEN` | WhatsApp Business API token | Required |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp phone number ID | Required |
| `SEARXNG_URL` | SearxNG instance URL | `http://localhost:4000` |
| `REDIS_URL` | Redis cache URL | `redis://localhost:6379` |
| `TTS_DEVICE` | TTS processing device | `mps` (Apple Silicon) |

### Performance Tuning

**For Apple Silicon Macs:**
```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1
export TTS_DEVICE=mps
```

**For CUDA GPUs:**
```bash
export TTS_DEVICE=cuda
```

**Memory Management:**
```bash
# Limit Redis memory
docker run redis:7-alpine redis-server --maxmemory 256mb

# TTS model caching
export TTS_CACHE_DIR=./cache/audio
```

## 📊 Monitoring

### Health Checks

```bash
# Overall health
curl http://localhost:8000/health

# Individual service health
curl http://localhost:8000/health | jq '.services'
```

### Statistics

Access user and system statistics via:
- Database queries in `/app/models/database.py`
- Service statistics in each service class
- WhatsApp API usage tracking

## 🐳 Deployment

### Docker Deployment

```bash
# Build and deploy
docker-compose up --build -d

# Scale for production
docker-compose up --scale api=3 -d
```

### Production Considerations

1. **Environment Security:**
   - Use Docker secrets for API keys
   - Configure SSL/TLS termination
   - Set up proper firewall rules

2. **Performance:**
   - Use PostgreSQL instead of SQLite
   - Redis cluster for high availability
   - Load balancer for multiple API instances

3. **Monitoring:**
   - Add Prometheus metrics
   - Configure log aggregation
   - Set up alerting for service failures

## 💰 Cost Analysis

### Free Tier Usage

**Groq API (FREE):**
- 30 requests/minute
- 14,400 requests/day  
- 30,000 tokens/minute
- Perfect for personal use and testing

**WhatsApp Business API:**
- 1,000 conversations/month free
- Service conversations completely free
- ~$0.05/conversation after free tier

**Self-hosted costs:**
- SearxNG: $0 (open source)
- XTTS-v2: $0 (runs locally)
- Redis: $0 (Docker container)

**Total for <1000 users/month: $0** 🎉

### Scale-up Costs

For 5,000+ users:
- VPS with GPU: ~$30-50/month
- WhatsApp API: ~$200/month  
- Groq upgrade: ~$10/month
- **Total: ~$250/month for 5K users**

## 🔧 Troubleshooting

### Common Issues

**1. TTS Model Not Loading:**
```bash
# For Apple Silicon
conda install pytorch torchvision -c pytorch
pip install TTS

# Test XTTS-v2
python -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

**2. WhatsApp Webhook Verification Failed:**
```bash
# Check webhook URL and verify token
curl "https://your-domain.com/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test"
```

**3. Groq API Rate Limits:**
```bash
# Monitor usage
python -c "from app.services.llm_service import LLMService; print(LLMService().get_usage_stats())"
```

**4. Search Service Not Working:**
```bash
# Check SearxNG
curl http://localhost:4000/search -d "q=test&format=json"

# Restart SearxNG
docker-compose restart searxng
```

### Logs

```bash
# View application logs
tail -f logs/perplexity_bot.log

# Docker logs
docker-compose logs -f api

# Specific service logs
docker-compose logs -f searxng
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Code formatting
black app/
flake8 app/

# Type checking
mypy app/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [SearxNG](https://github.com/searxng/searxng) - Privacy-respecting web search
- [Groq](https://groq.com/) - Fast LLM inference
- [Coqui TTS](https://github.com/coqui-ai/TTS) - Open source text-to-speech
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp) - Messaging platform

---

**🚀 Ready to deploy your own Perplexity-like WhatsApp bot!**

For questions and support, create an issue in the repository.