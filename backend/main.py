from datetime import date
from datetime import datetime, timedelta
from services import sync_nba_games # Importer vores nye sync-funktion
from services import get_game_rosters
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="NBA Pick 'em API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Tillad din fremtidige Vue-dev-server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nba_user:secret_password@localhost:5432/nba_db")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- Pydantic Schemas ---
class UserCreate(BaseModel):
    username: str
    email: str

class PredictionCreate(BaseModel):
    user_id: int
    game_id: int
    predicted_winner_id: int

# --- Existing Endpoints ---
@app.get("/games")
def get_games():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            g.id, g.game_date, g.home_score, g.away_score, g.status,
            ht.full_name AS home_team, ht.abbreviation AS home_team_abbrev,
            at.full_name AS away_team, at.abbreviation AS away_team_abbrev
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.id
        JOIN teams at ON g.away_team_id = at.id
        WHERE g.status != 'Final'
        ORDER BY g.game_date ASC;
    """)
    games = cur.fetchall()
    cur.close()
    conn.close()
    return {"games": games}

@app.get("/games/finished")
def get_finished_games():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            g.id, g.game_date, g.home_score, g.away_score, g.status,
            ht.full_name AS home_team, ht.abbreviation AS home_team_abbrev,
            at.full_name AS away_team, at.abbreviation AS away_team_abbrev
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.id
        JOIN teams at ON g.away_team_id = at.id
        WHERE g.status = 'Final'
          AND g.game_date::date >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY g.game_date DESC;
    """)
    games = cur.fetchall()
    cur.close()
    conn.close()
    return {"finished_games": games}

# Global variabel til at holde styr på seneste sync-tidspunkt i hukommelsen
last_sync_time = datetime.now() - timedelta(hours=1)

# --- Endpoint til "Opdater data"-knap ---
@app.post("/games/refresh")
def refresh_games():
    global last_sync_time
    success = sync_nba_games()
    if not success:
        raise HTTPException(status_code=500, detail="Kunne ikke hente nye data fra BallDontLie API.")
    
    last_sync_time = datetime.now()
    return {"message": "Kampe blev opdateret succesfuldt!"}

# --- New User Endpoints ---
@app.post("/users", status_code=201)
def create_user(user: UserCreate):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id, username, email;",
            (user.username, user.email)
        )
        new_user = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Username eller email findes allerede.")
    
    cur.close()
    conn.close()
    return new_user

# --- New Prediction Endpoints ---
@app.post("/predictions")
def make_prediction(pred: PredictionCreate):
    global last_sync_time
    
    # Hvis data er ældre end 5 minutter, og en bruger laver en prediction: refresh automatisk!
    if datetime.now() - last_sync_time > timedelta(minutes=5):
        try:
            if sync_nba_games():
                last_sync_time = datetime.now()
        except Exception as e:
            # Hvis API'et driller, fortsætter vi blot med eksisterende DB-data
            print(f"Automatisk sync fejlede: {e}")

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT status, game_date, home_team_id, away_team_id 
        FROM games 
        WHERE id = %s;
    """, (pred.game_id,))
    game = cur.fetchone()
    
    if not game:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Kamp ikke fundet.")
        
    # 1. Tjek om kampen er markeret som Final eller har ændret status fra 'Scheduled'
    if game['status'] == 'Final' or game['status'] != 'Scheduled':
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400, 
            detail="Kampen er allerede afsluttet eller i gang. Forudsigelser er låst."
        )

    # 2. Tjek om kampdatoen er en tidligere dato end i dag
    game_date_only = game['game_date'].date() if hasattr(game['game_date'], 'date') else game['game_date']
    if game_date_only < date.today():
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400, 
            detail="Datoen for denne kamp er passeret. Forudsigelser er låst."
        )

    # 3. Tjek om det valgte hold spiller i kampen
    if pred.predicted_winner_id not in [game['home_team_id'], game['away_team_id']]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Det valgte hold spiller ikke i denne kamp.")

    # Indsæt eller opdater gæt (UPSERT)
    cur.execute("""
        INSERT INTO predictions (user_id, game_id, predicted_winner_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, game_id) 
        DO UPDATE SET predicted_winner_id = EXCLUDED.predicted_winner_id, created_at = CURRENT_TIMESTAMP
        RETURNING id, user_id, game_id, predicted_winner_id;
    """, (pred.user_id, pred.game_id, pred.predicted_winner_id))
    
    saved_prediction = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    return {"message": "Prediction gemt succesfuldt!", "prediction": saved_prediction}

@app.get("/users/{user_id}/predictions")
def get_user_predictions(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            p.id AS prediction_id,
            g.id AS game_id,
            g.game_date,
            g.status AS game_status,
            ht.abbreviation AS home_team,
            at.abbreviation AS away_team,
            pt.full_name AS predicted_winner,
            pt.id AS predicted_winner_id,
            CASE 
                WHEN g.status != 'Final' THEN 'Pending'
                WHEN (g.home_score > g.away_score AND p.predicted_winner_id = g.home_team_id) OR
                     (g.away_score > g.home_score AND p.predicted_winner_id = g.away_team_id) THEN 'Correct'
                ELSE 'Incorrect'
            END AS result
        FROM predictions p
        JOIN games g ON p.game_id = g.id
        JOIN teams ht ON g.home_team_id = ht.id
        JOIN teams at ON g.away_team_id = at.id
        JOIN teams pt ON p.predicted_winner_id = pt.id
        WHERE p.user_id = %s
        ORDER BY g.game_date DESC;
    """, (user_id,))
    
    predictions = cur.fetchall()
    cur.close()
    conn.close()
    
    return {"user_id": user_id, "predictions": predictions}

@app.get("/users/{user_id}/my-predictions")
def get_user_my_predictions(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Aktuelle/kommende gæt (hvor kampen ikke er afsluttet endnu)
    cur.execute("""
        SELECT 
            p.id AS prediction_id,
            g.id AS game_id,
            g.game_date,
            g.status AS game_status,
            ht.abbreviation AS home_team,
            at.abbreviation AS away_team,
            pt.full_name AS predicted_winner,
            pt.id AS predicted_winner_id
        FROM predictions p
        JOIN games g ON p.game_id = g.id
        JOIN teams ht ON g.home_team_id = ht.id
        JOIN teams at ON g.away_team_id = at.id
        JOIN teams pt ON p.predicted_winner_id = pt.id
        WHERE p.user_id = %s AND g.status != 'Final'
        ORDER BY g.game_date ASC;
    """, (user_id,))
    active_predictions = cur.fetchall()
    
    # 2. Historik over afsluttede kampe (inkl. kampe der IKKE er gættet på)
    cur.execute("""
        SELECT 
            g.id AS game_id,
            g.game_date,
            g.status AS game_status,
            g.home_score,
            g.away_score,
            ht.abbreviation AS home_team,
            at.abbreviation AS away_team,
            CASE 
                WHEN g.home_score > g.away_score THEN ht.full_name
                ELSE at.full_name
            END AS actual_winner,
            pt.full_name AS predicted_winner,
            CASE 
                WHEN p.id IS NULL THEN 'No Prediction'
                WHEN (g.home_score > g.away_score AND p.predicted_winner_id = g.home_team_id) OR
                     (g.away_score > g.home_score AND p.predicted_winner_id = g.away_team_id) THEN 'Correct'
                ELSE 'Incorrect'
            END AS result
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.id
        JOIN teams at ON g.away_team_id = at.id
        LEFT JOIN predictions p ON g.id = p.game_id AND p.user_id = %s
        LEFT JOIN teams pt ON p.predicted_winner_id = pt.id
        WHERE g.status = 'Final'
        ORDER BY g.game_date DESC;
    """, (user_id,))
    history = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return {
        "user_id": user_id,
        "active_predictions": active_predictions,
        "history": history
    }

@app.get("/games/{game_id}/rosters")
def get_rosters(game_id: int):
    rosters = get_game_rosters(game_id)
    if rosters is None:
        raise HTTPException(status_code=404, detail="Kampen blev ikke fundet.")
    return rosters