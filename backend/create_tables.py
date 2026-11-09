import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nba_user:secret_password@localhost:5432/nba_db")

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Opret users tabel
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Opret predictions tabel
    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            game_id INT REFERENCES games(id) ON DELETE CASCADE,
            predicted_winner_id INT REFERENCES teams(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_user_game UNIQUE (user_id, game_id)
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("Tabellerne 'users' og 'predictions' er oprettet i databasen!")

if __name__ == "__main__":
    init_db()