-- Tabeller til NBA Hub

-- 1. Brugere
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Hold (Teams)
CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    abbreviation VARCHAR(10) UNIQUE NOT NULL, -- f.eks. 'NYK'
    full_name VARCHAR(100) NOT NULL,          -- f.eks. 'New York Knicks'
    conference VARCHAR(20)                    -- 'East' eller 'West'
);

-- 3. Mange-til-mange relation for yndlingshold
CREATE TABLE user_favorite_teams (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, team_id)
);

-- 4. Kampe (Games)
CREATE TABLE games (
    id SERIAL PRIMARY KEY,
    game_date TIMESTAMP NOT NULL,
    home_team_id INT REFERENCES teams(id),
    away_team_id INT REFERENCES teams(id),
    home_score INT DEFAULT 0,
    away_score INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'Scheduled' -- 'Scheduled', 'Live', 'Final'
);

-- 5. Brugerens gæt på kampe (Pick 'em / Spil på Kampe)
CREATE TABLE user_predictions (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    game_id INT REFERENCES games(id) ON DELETE CASCADE,
    predicted_winner_id INT REFERENCES teams(id),
    is_correct BOOLEAN DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, game_id) -- En bruger kan kun gætte én gang per kamp
);