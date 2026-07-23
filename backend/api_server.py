"""
api_server.py — Servidor FastAPI para el torneo de Fortnite.
Sistema basado en importación de Replays (sin OCR).
"""
import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Imports locales ──────────────────────────────────────────────────────────
from .config import config, save_config
from .database import (
    SessionLocal, init_db, get_db,
    get_all_players, get_player_by_username, create_player, delete_player,
    get_all_matches, delete_match, MatchResult,
    upsert_match_result
)
from .scoring_engine import build_standings, recalculate_all_matches
from . import replay_api

# ─── Inicialización ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI(title="Torneo Fortnite - Sistema de Replays", version="2.0.0")

app.include_router(replay_api.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar base de datos
init_db()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class PlayerCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    is_pro: bool = False


class TournamentNamePayload(BaseModel):
    name: str


class ProBonusPayload(BaseModel):
    bonus: int


# ─── Players API ──────────────────────────────────────────────────────────────

@app.get("/api/players")
def list_players(db=Depends(get_db)):
    players = get_all_players(db)
    return [
        {"id": p.id, "username": p.username, "display_name": p.display_name or p.username, "is_pro": p.is_pro}
        for p in players
    ]


@app.post("/api/players", status_code=201)
def add_player(body: PlayerCreate, db=Depends(get_db)):
    existing = get_player_by_username(db, body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Jugador ya registrado")
    player = create_player(db, body.username, body.display_name, body.is_pro)
    return {"id": player.id, "username": player.username, "display_name": player.display_name, "is_pro": player.is_pro}


@app.delete("/api/players/{player_id}")
def remove_player(player_id: int, db=Depends(get_db)):
    ok = delete_player(db, player_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")
    return {"ok": True}


@app.put("/api/players/{player_id}/toggle-pro")
def toggle_player_pro(player_id: int, db=Depends(get_db)):
    from .database import Player
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")
    
    player.is_pro = not player.is_pro
    db.commit()
    
    # Re-calculate matches so past points adjust to the new category
    recalculate_all_matches(db)
    
    return {"id": player.id, "is_pro": player.is_pro}


# ─── Standings API ────────────────────────────────────────────────────────────

@app.get("/api/standings")
def get_standings(db=Depends(get_db)):
    return build_standings(db)


@app.get("/api/matches")
def list_matches(db=Depends(get_db)):
    matches = get_all_matches(db)
    return [
        {
            "id": m.id,
            "match_number": m.match_number,
            "is_active": m.is_active,
            "started_at": m.started_at.isoformat() if m.started_at else None,
            "ended_at": m.ended_at.isoformat() if m.ended_at else None,
        }
        for m in matches
    ]


@app.get("/api/matches/{match_id}/results")
def get_match_results_api(match_id: int, db=Depends(get_db)):
    from .database import get_match_results
    rows = get_match_results(db, match_id)
    results = []
    for rank, row in enumerate(rows, start=1):
        results.append({
            "rank": rank,
            "player_id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "is_pro": bool(row.is_pro),
            "position": row.position,
            "kills": row.kills,
            "kill_adjustment": row.kill_adjustment or 0,
            "bonus_points": row.bonus_points or 0,
            "placement_points": row.placement_points,
            "kill_points": row.kill_points,
            "total_points": row.total_points,
        })
    return results


class AdjustmentPayload(BaseModel):
    username: str
    adjustment: int


@app.put("/api/matches/{match_id}/results/adjust")
def adjust_match_kills(match_id: int, payload: AdjustmentPayload, db=Depends(get_db)):
    from .database import get_player_by_username, upsert_match_result
    from .scoring_engine import recalculate_match

    player = get_player_by_username(db, payload.username)
    if not player:
        raise HTTPException(404, f"Jugador '{payload.username}' no encontrado")

    result = db.query(MatchResult).filter(
        MatchResult.match_id == match_id,
        MatchResult.player_id == player.id
    ).first()
    if not result:
        raise HTTPException(404, "Resultado no encontrado")

    result.kill_adjustment = payload.adjustment
    db.commit()

    recalculate_match(db, match_id)

    return {"ok": True}


class BonusPayload(BaseModel):
    username: str
    bonus: int


@app.put("/api/matches/{match_id}/results/bonus")
def adjust_match_bonus(match_id: int, payload: BonusPayload, db=Depends(get_db)):
    from .database import get_player_by_username
    from .scoring_engine import recalculate_match

    player = get_player_by_username(db, payload.username)
    if not player:
        raise HTTPException(404, f"Jugador '{payload.username}' no encontrado")

    result = db.query(MatchResult).filter(
        MatchResult.match_id == match_id,
        MatchResult.player_id == player.id
    ).first()
    if not result:
        raise HTTPException(404, "Resultado no encontrado")

    result.bonus_points = payload.bonus
    db.commit()

    recalculate_match(db, match_id)

    return {"ok": True}


@app.delete("/api/matches/{match_id}")
def remove_match(match_id: int, db=Depends(get_db)):
    from .database import delete_match
    ok = delete_match(db, match_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    return {"ok": True}


@app.get("/api/matches/{match_id}/eliminations")
def get_match_eliminations(match_id: int, db=Depends(get_db)):
    from .database import Elimination
    
    elims = db.query(Elimination).filter(Elimination.match_id == match_id).order_by(Elimination.timestamp.asc(), Elimination.id.asc()).all()
    
    # Si las eliminaciones vienen del replay feed, `raw_text` es `[REPLAY_FEED]`.
    # Vamos a devolverlas limpias.
    result = []
    for e in elims:
        # Filtramos los dummies creados por la importacion manual o bots
        if e.raw_text == "[REPLAY_IMPORT]":
            continue
        result.append({
            "eliminator": e.eliminator_username,
            "eliminated": e.eliminated_username,
            "weapon": e.weapon,
            "gun_type": e.gun_type,
            "distance": e.distance,
            "is_self_elimination": bool(e.is_self_elimination),
            "is_npc_elimination": bool(e.is_npc_elimination),
            "is_bot_elimination": bool(e.is_bot_elimination),
            "event_tags": e.event_tags,
            "display_text": e.display_text,
            "time": e.match_time,
            "confidence": e.confidence
        })
    return result


# ─── Config API ───────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return {
        "tournament_name": config.tournament_name,
        "kill_points": config.kill_points,
        "placement_points": config.placement_points,
        "casual_points": config.casual_points,
        "pro_points": config.pro_points,
        "max_matches": config.max_matches,
        "pro_bonus_points": getattr(config, "pro_bonus_points", 0),
    }


@app.put("/api/config/name")
def update_name(body: TournamentNamePayload):
    config.tournament_name = body.name
    save_config(config)
    return {"ok": True}


@app.put("/api/config/pro-bonus")
def update_pro_bonus(body: ProBonusPayload, db=Depends(get_db)):
    config.pro_bonus_points = body.bonus
    save_config(config)
    
    # Recalculate matches to apply the new bonus
    recalculate_all_matches(db)
    return {"ok": True}


class ScoringPayload(BaseModel):
    casual_points: dict
    pro_points: dict
    casual_kill_points: Optional[int] = None
    pro_kill_points: Optional[int] = None


@app.get("/api/scoring")
def get_scoring():
    return {
        "casual_points": config.casual_points,
        "pro_points": config.pro_points,
        "casual_kill_points": config.casual_kill_points,
        "pro_kill_points": config.pro_kill_points,
    }


@app.put("/api/scoring")
def update_scoring(body: ScoringPayload, db=Depends(get_db)):
    config.casual_points = {int(k): v for k, v in body.casual_points.items()}
    config.pro_points = {int(k): v for k, v in body.pro_points.items()}
    if body.casual_kill_points is not None:
        config.casual_kill_points = body.casual_kill_points
    if body.pro_kill_points is not None:
        config.pro_kill_points = body.pro_kill_points
    save_config(config)

    recalculate_all_matches(db)

    return {"ok": True}


# ─── Static files (frontend) ───────────────────────────────────────────────────

if os.path.exists(FRONTEND_DIR):
    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        if not path:
            path = "index.html"
        file_path = os.path.join(FRONTEND_DIR, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
