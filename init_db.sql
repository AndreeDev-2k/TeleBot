CREATE TABLE users (
	  id SERIAL PRIMARY KEY,
	  telegram_id BIGINT UNIQUE NOT NULL
);

CREATE TABLE shops (
	  id SERIAL PRIMARY KEY,
	  shop_name TEXT UNIQUE NOT NULL,
	  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE subscriptions (
	  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
	  shop_id INTEGER REFERENCES shops(id) ON DELETE CASCADE,
	  PRIMARY KEY (user_id, shop_id)
);

CREATE TABLE last_seen (
	  shop_id INTEGER PRIMARY KEY REFERENCES shops(id),
	  listing_id TEXT NOT NULL,
	  seen_at TIMESTAMP DEFAULT NOW()
);
