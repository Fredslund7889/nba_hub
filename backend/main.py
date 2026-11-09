from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="NBA Pick 'em API")

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
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tjek om kampen findes og ikke er afsluttet endnu
    cur.execute("SELECT status, home_team_id, away_team_id FROM games WHERE id = %s;", (pred.game_id,))
    game = cur.fetchone()
    
    if not game:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Kamp ikke fundet.")
        
    if game['status'] == 'Final':
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Kampen er allerede afsluttet. Du kan ikke afgive gæt.")

    if pred.predicted_winner_id not in [game['home_team_id'], game['away_team_id']]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Det valgte hold spiller ikke i denne kamp.")

    # Indsæt eller opdater eksisterende gæt (UPSERT)
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
    
    return {"message": "Prediction gemt!", "prediction": saved_prediction}

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