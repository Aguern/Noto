-- Migrations for news briefing pipeline
-- Run these SQL commands to update the database schema

-- Add new fields to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS locale VARCHAR(10) DEFAULT 'fr_FR';
ALTER TABLE users ADD COLUMN IF NOT EXISTS wants_audio BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS voice_ref VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_channel VARCHAR(50) DEFAULT 'whatsapp';

-- Create user_topics table for managing user interests
CREATE TABLE IF NOT EXISTS user_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic VARCHAR(255) NOT NULL,
    frequency VARCHAR(50) DEFAULT 'quotidien', -- quotidien, lundi, 2x_semaine, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, topic)
);

-- Create deliveries table for tracking sent briefs
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    channel VARCHAR(50) DEFAULT 'whatsapp',
    text_len INTEGER,
    audio_path VARCHAR(500),
    citations_json TEXT, -- JSON array of citations
    topic VARCHAR(255),
    time_range VARCHAR(10), -- 24h or 72h
    items_count INTEGER,
    processing_time_ms INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_topics_user_id ON user_topics(user_id);
CREATE INDEX IF NOT EXISTS idx_user_topics_frequency ON user_topics(frequency);
CREATE INDEX IF NOT EXISTS idx_deliveries_user_id ON deliveries(user_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_sent_at ON deliveries(sent_at);

-- Add wants_audio field to preferences table if not exists
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS wants_audio BOOLEAN DEFAULT FALSE;

-- Sample data for testing (optional)
-- INSERT INTO user_topics (user_id, topic, frequency) VALUES 
-- (1, 'tech', 'quotidien'),
-- (1, 'économie', '2x_semaine'),
-- (1, 'sport', 'lundi');