import os
import requests
import psycopg2
from datetime import date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nba_user:secret_password@db:5432/nba_db")
API_KEY = os.getenv("BALLDONTLIE_API_KEY")

def sync_nba_games():
    """Henter kampe fra BallDontLie for en 3-dages rullende vindue og opdaterer PostgreSQL."""
    if not API_KEY:
        print("Advarsel: BALLDONTLIE_API_KEY er ikke sat.")
        return False

    headers = {"Authorization": API_KEY}
    
    # 3-dages rullende vindue (i går, i dag, i morgen)
    today = date.today()
    dates = [
        (today - timedelta(days=1)).strftime('%Y-%m-%d'),
        today.strftime('%Y-%m-%d'),
        (today + timedelta(days=1)).strftime('%Y-%m-%d')
    ]
    
    url = "https://api.balldontlie.io/v1/games"
    params = {"dates[]": dates, "per_page": 100}
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Fejl fra BallDontLie API: {response.status_code}")
        return False
        
    data = response.json().get("data", [])
    if not data:
        print("Ingen kampe fundet i API-responset.")
        return True

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    synced_count = 0
    for g in data:
        # Brug .get() for at undgå KeyError hvis et felt mangler i et API-svar
        game_id = g.get("id")
        game_date = g.get("date")
        home_team = g.get("home_team")
        away_team = g.get("away_team")
        
        if not home_team or not away_team:
            continue # Spring over hvis hold-data mangler
            
        home_team_id = home_team.get("id")
        away_team_id = away_team.get("id")
        home_score = g.get("home_score", 0) or 0
        away_score = g.get("away_score", 0) or 0
        status = g.get("status", "Scheduled")
        
        # Indsæt eller opdater kampen (UPSERT)
        cur.execute("""
            INSERT INTO games (id, game_date, home_team_id, away_team_id, home_score, away_score, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) 
            DO UPDATE SET 
                home_score = EXCLUDED.home_score,
                away_score = EXCLUDED.away_score,
                status = EXCLUDED.status,
                game_date = EXCLUDED.game_date;
        """, (game_id, game_date, home_team_id, away_team_id, home_score, away_score, status))
        synced_count += 1
        
    conn.commit()
    cur.close()
    conn.close()
    print(f"Synkroniseret {synced_count} kampe succesfuldt.")
    return True

def get_game_rosters(game_id: int):
    """Henter hold og spillere for en specifik kamp via vores egen database og BallDontLie API (kun spillere med trøjenummer)."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Hent hold-ID'erne for den valgte kamp fra vores database
    cur.execute("""
        SELECT home_team_id, away_team_id 
        FROM games 
        WHERE id = %s;
    """, (game_id,))
    game_teams = cur.fetchone()
    cur.close()
    conn.close()
    
    if not game_teams:
        return None
        
    home_team_id, away_team_id = game_teams
    
    # Hent spillere fra BallDontLie API for begge hold
    headers = {"Authorization": API_KEY}
    url = "https://api.balldontlie.io/v1/players"
    
    def fetch_players_for_team(team_id):
        params = {"team_ids[]": [team_id], "per_page": 100}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            return resp.json().get("data", [])
        return []

    home_players = fetch_players_for_team(home_team_id)
    away_players = fetch_players_for_team(away_team_id)
    
    # Filtrer og formatér dataen (fravælg spillere uden trøjenummer)
    def format_players(players):
        filtered_players = [p for p in players if p.get("jersey_number") not in (None, "")]
        return [{
            "id": p.get("id"),
            "first_name": p.get("first_name"),
            "last_name": p.get("last_name"),
            "position": p.get("position"),
            "jersey_number": p.get("jersey_number")
        } for p in filtered_players]

    return {
        "game_id": game_id,
        "home_team_players": format_players(home_players),
        "away_team_players": format_players(away_players)
    }