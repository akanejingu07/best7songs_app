CREATE TABLE best_songs (
  id SERIAL PRIMARY KEY,
  song_title TEXT NOT NULL,
  artist TEXT NOT NULL,
  url TEXT,
  rating INTEGER,
  reason TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
