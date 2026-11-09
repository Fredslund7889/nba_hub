import os
import psycopg2
from nba_api.stats.static import teams

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nba_user:secret_password@localhost:5432/nba_db")

def seed_teams():
    print("Henter NBA-hold fra nba_api...")
    nba_teams = teams.get_teams()
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    inserted_count = 0
    for team in nba_teams:
        # Forbered data
        abbreviation = team['abbreviation']
        full_name = team['full_name']
        
        # Simpel inddeling af Eastern / Western conference ud fra velkendte forkortelser
        east_teams = ['BOS', 'BKN', 'NYK', 'PHI', 'TOR', 'CHI', 'CLE', 'DET', 'IND', 'MIL', 'ATL', 'CHA', 'MIA', 'ORL', 'WAS']
        conference = 'East' if abbreviation in east_teams else 'West'
        
        # Indsæt i PostgreSQL (ON CONFLICT DO NOTHING gør, at vi kan køre scriptet flere gange uden fejl)
        cur.execute("""
            INSERT INTO teams (abbreviation, full_name, conference)
            VALUES (%s, %s, %s)
            ON CONFLICT (abbreviation) DO NOTHING;
        """, (abbreviation, full_name, conference))
        inserted_count += cur.rowcount
        
    conn.commit()
    cur.close()
    conn.close()
    print(f"Færdig! Indsatte/opdaterede hold i databasen.")

if __name__ == "__main__":
    seed_teams()