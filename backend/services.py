import os
import requests
import psycopg2
from datetime import date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nba_user:secret_password@db:5432/nba_db")
API_KEY = os.getenv("BALLDONTLIE_API_KEY")

# Mapping fra holdets abbreviation til Bell Media / TSN competitor ID
BELL_MEDIA_TEAM_IDS = {
    "ATL": 1,   # Atlanta Hawks
    "BOS": 2,   # Boston Celtics
    "BKN": 17,   # Brooklyn Nets
    "CHA": 5312,   # Charlotte Hornets
    "CHI": 4,   # Chicago Bulls
    "CLE": 5,   # Cleveland Cavaliers
    "DAL": 6,   # Dallas Mavericks
    "DEN": 7,   # Denver Nuggets
    "DET": 8,   # Detroit Pistons
    "GSW": 9,  # Golden State Warriors
    "HOU": 10,  # Houston Rockets
    "IND": 11,  # Indiana Pacers
    "LAC": 12,  # LA Clippers
    "LAL": 13,  # Los Angeles Lakers
    "MEM": 29,  # Memphis Grizzlies
    "MIA": 14,  # Miami Heat
    "MIL": 15,  # Milwaukee Bucks
    "MIN": 16,  # Minnesota Timberwolves
    "NOP": 3,  # New Orleans Pelicans
    "NYK": 18,  # New York Knicks
    "OKC": 25,  # Oklahoma City Thunder
    "ORL": 19,  # Orlando Magic
    "PHI": 20,  # Philadelphia 76ers
    "PHX": 21,  # Phoenix Suns
    "POR": 22,  # Portland Trail Blazers
    "SAC": 23,  # Sacramento Kings
    "SAS": 24,  # San Antonio Spurs
    "TOR": 28,  # Toronto Raptors
    "UTA": 26,  # Utah Jazz
    "WAS": 27,  # Washington Wizards
}

def sync_nba_games():
    """Henter kampe fra BallDontLie for et 3-dages rullende vindue og opdaterer PostgreSQL."""
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
        game_id = g.get("id")
        game_date = g.get("date")
        home_team = g.get("home_team")
        away_team = g.get("away_team")
        
        if not home_team or not away_team:
            continue
            
        home_team_id = home_team.get("id")
        away_team_id = away_team.get("id")
        home_score = g.get("home_score", 0) or 0
        away_score = g.get("away_score", 0) or 0
        status = g.get("status", "Scheduled")
        
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

def fetch_tsn_roster(team_abbrev: str):
    """Henter den aktuelle trup via Bell Media / TSN API."""
    tsn_id = BELL_MEDIA_TEAM_IDS.get(team_abbrev)
    if not tsn_id:
        print(f"[TSN API Warning] Ukendt holdforkortelse: {team_abbrev}", flush=True)
        return []

    url = f"https://next-gen.sports.bellmedia.ca/v2/competitor/basketball/nba/{tsn_id}/roster?brand=tsn&lang=en"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
        "Referer": "https://www.tsn.ca/"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            print(f"[TSN API Error] Status {resp.status_code} for {team_abbrev}", flush=True)
            return []

        data = resp.json()

        # Responsen er en liste, men vær defensiv hvis den ændrer sig til et objekt
        if isinstance(data, list):
            players_data = data
        else:
            players_data = data.get("players") or data.get("roster") or []

        formatted_players = []
        for p in players_data:
            jersey = p.get("number")
            if jersey is None:
                continue

            formatted_players.append({
                "id": p.get("playerId"),
                "first_name": p.get("firstName") or "",
                "last_name": p.get("lastName") or "",
                "position": p.get("positionShort") or p.get("position"),
                "jersey_number": str(jersey),
                "photo_url": None,  # Ikke i TSN roster-payload
            })
        return formatted_players

    except Exception as e:
        print(f"[TSN API Exception] Fejl ved hentning af {team_abbrev}: {e}", flush=True)

    return []

def get_game_rosters(game_id: int):
    """Henter hold og aktive trupper for en kamp via databasen og TSN API."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Henter holdenes forkortelser (f.eks. 'ATL', 'NYK') via JOIN
        cur.execute("""
            SELECT 
                h.abbreviation AS home_abbrev, 
                a.abbreviation AS away_abbrev
            FROM games g
            JOIN teams h ON g.home_team_id = h.id
            JOIN teams a ON g.away_team_id = a.id
            WHERE g.id = %s;
        """, (game_id,))
        
        game_teams = cur.fetchone()
        cur.close()
        conn.close()
        
        if not game_teams:
            return None
            
        home_abbrev, away_abbrev = game_teams

        return {
            "game_id": game_id,
            "home_team_players": fetch_tsn_roster(home_abbrev),
            "away_team_players": fetch_tsn_roster(away_abbrev)
        }
    except Exception as e:
        print(f"[Backend Error] Exception i get_game_rosters: {e}")
        return {
            "game_id": game_id,
            "home_team_players": [],
            "away_team_players": []
        }