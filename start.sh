#!/bin/bash

# Perplexity WhatsApp Bot - Quick Start Script
echo "🚀 Starting Perplexity WhatsApp Bot..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please copy and configure your .env file."
    echo "   cp .env.example .env"
    echo "   # Then edit .env with your API keys"
    exit 1
fi

# Start supporting services
echo "🐳 Starting Docker services (Redis + SearxNG)..."
docker-compose up -d redis searxng

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check if conda environment exists
if command -v conda &> /dev/null; then
    echo "🐍 Conda detected. Checking environment..."
    if ! conda env list | grep -q "perplexity-bot"; then
        echo "📦 Creating conda environment..."
        conda create -n perplexity-bot python=3.10 -y
        echo "📦 Installing PyTorch..."
        conda run -n perplexity-bot conda install pytorch torchvision -c pytorch -y
        echo "📦 Installing Python packages..."
        conda run -n perplexity-bot pip install -r requirements.txt
        conda run -n perplexity-bot pip install TTS
    fi
    
    # Initialize database
    echo "🗄️ Initializing database..."
    conda run -n perplexity-bot python -c "from app.models.database import init_db; init_db()"
    
    # Run tests
    echo "🧪 Running pipeline tests..."
    conda run -n perplexity-bot python test_pipeline.py
    
    if [ $? -eq 0 ]; then
        echo "✅ Tests passed! Starting bot..."
        echo "🌐 Bot will be available at http://localhost:8000"
        echo "📱 Webhook endpoint: http://localhost:8000/webhook"
        echo ""
        echo "💡 For public access, use ngrok:"
        echo "   ngrok http 8000"
        echo ""
        conda run -n perplexity-bot python app/api/main.py
    else
        echo "❌ Tests failed. Please check the configuration."
        exit 1
    fi
    
else
    # Without conda
    echo "🐍 Using system Python..."
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo "📦 Creating virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        pip install TTS
    else
        source venv/bin/activate
    fi
    
    # Initialize database
    echo "🗄️ Initializing database..."
    python -c "from app.models.database import init_db; init_db()"
    
    # Run tests
    echo "🧪 Running pipeline tests..."
    python test_pipeline.py
    
    if [ $? -eq 0 ]; then
        echo "✅ Tests passed! Starting bot..."
        echo "🌐 Bot will be available at http://localhost:8000"
        echo "📱 Webhook endpoint: http://localhost:8000/webhook"
        echo ""
        echo "💡 For public access, use ngrok:"
        echo "   ngrok http 8000"
        echo ""
        python app/api/main.py
    else
        echo "❌ Tests failed. Please check the configuration."
        exit 1
    fi
fi