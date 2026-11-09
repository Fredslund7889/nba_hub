import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nba_user:secret_password@localhost:5432/nba_db")
BALLDONTLIE_API_URL = "https://api.balldontlie.io/v1/games"

BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY")

HEADERS = {
    'Authorization': BALLDONTLIE_API_KEY
}

def fetch_and_save_games():
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    print(f"Henter kampe for vinduet: {yesterday_str} til {tomorrow_str}...")
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    # Nulstil tabellen, så vi altid har et rent 3-dages rullende overblik
    cur.execute("TRUNCATE TABLE games RESTART IDENTITY CASCADE;")
    
    # Hent hold-mapping
    cur.execute("SELECT id, abbreviation FROM teams;")
    team_map = {row['abbreviation']: row['id'] for row in cur.fetchall()}
    
    params = {
        'dates[]': [yesterday_str, today_str, tomorrow_str],
        'per_page': 100
    }
    
    try:
        response = requests.get(BALLDONTLIE_API_URL, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        games_data = response.json().get('data', [])
    except Exception as e:
        print(f"Fejl ved forespørgsel til BallDontLie: {e}")
        conn.close()
        return

    inserted_count = 0
    for g in games_data:
        home_abbrev = g.get('home_team', {}).get('abbreviation')
        away_abbrev = g.get('visitor_team', {}).get('abbreviation')
        
        if home_abbrev not in team_map or away_abbrev not in team_map:
            continue
            
        home_score = g.get('home_team_score', 0) or 0
        away_score = g.get('visitor_team_score', 0) or 0
        
        status_str = g.get('status', '')
        is_final = 'Final' in status_str or status_str == 'Final'
        status = 'Final' if is_final else 'Scheduled'
        game_date = g.get('date', '')

        cur.execute("""
            INSERT INTO games (game_date, home_team_id, away_team_id, home_score, away_score, status)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (
            game_date,
            team_map[home_abbrev],
            team_map[away_abbrev],
            home_score,
            away_score,
            status
        ))
        inserted_count += 1
            
    conn.commit()
    cur.close()
    conn.close()
    print(f"Færdig! Indsatte {inserted_count} kampe (inkl. resultater fra i går) i databasen.")

if __name__ == "__main__":
    fetch_and_save_games()