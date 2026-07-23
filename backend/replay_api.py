"""
replay_api.py — Endpoints de la API para importar replays de Fortnite.
Se monta sobre el servidor FastAPI existente.
"""
import os
import json
import shutil
import tempfile
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel

from .database import (
    SessionLocal, get_db, get_all_players, get_active_match,
    create_match, add_elimination, upsert_match_result, get_all_matches,
    get_player_by_username, create_player,
)
from .scoring_engine import get_placement_points, get_kill_points, build_standings
from .replay_importer import (
    parse_replay, list_replays, get_latest_replay, FORTNITE_REPLAY_DIR
)

router = APIRouter(prefix="/api/replay", tags=["replay"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ManualImportPayload(BaseModel):
    """Payload para importación manual de resultados de una partida."""
    match_number: Optional[int] = None
    results: List[dict]  # [{username, kills, position}]
    eliminations: Optional[List[dict]] = []  # Detalle del killfeed


class ReplayImportResult(BaseModel):
    source: str
    eliminations: list
    placements: dict
    possible_players: list = []
    message: str = ""


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/list")
def list_local_replays():
    """Lista los replays disponibles en la carpeta de Fortnite."""
    replays = list_replays(n=15)
    return {
        "replay_dir": FORTNITE_REPLAY_DIR,
        "dir_exists": os.path.exists(FORTNITE_REPLAY_DIR),
        "replays": replays,
    }


@router.get("/latest")
def get_latest(debug: bool = False, db=Depends(get_db)):
    """Obtiene el replay más reciente y lo parsea."""
    path = get_latest_replay()
    if not path:
        raise HTTPException(404, "No se encontró ningún archivo .replay en la carpeta de Fortnite.")
        
    known_players = [p.username for p in get_all_players(db)]
    result = parse_replay(path, known_players, debug=debug)
    result["filename"] = os.path.basename(path)
    return result


@router.post("/upload")
async def upload_replay(file: UploadFile = File(...), debug: bool = False, db=Depends(get_db)):
    """Permite subir un archivo .replay manualmente para parsearlo."""
    if not file.filename.endswith(".replay"):
        raise HTTPException(400, "El archivo debe tener extensión .replay")

    # Guardar temporalmente
    with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        known_players = [p.username for p in get_all_players(db)]
        result = parse_replay(tmp_path, known_players, debug=debug)
        result["filename"] = file.filename
        return result
    finally:
        os.unlink(tmp_path)


@router.post("/import-manual")
async def import_manual_results(payload: ManualImportPayload, db=Depends(get_db)):
    """
    Importa resultados de una partida manualmente (kills + posiciones).
    Crea la partida siempre como nueva.
    """
    import traceback
    from sqlalchemy.exc import IntegrityError

    def get_or_create_player(db, username):
        """Busca el jugador o lo crea; maneja UNIQUE constraint si ya existe."""
        player = get_player_by_username(db, username)
        if player:
            return player
        try:
            player = create_player(db, username, username)
            return player
        except IntegrityError:
            db.rollback()
            # Ya fue insertado por otra ruta (race condition o entrada duplicada)
            player = get_player_by_username(db, username)
            if player:
                return player
            raise

    try:
        # Crear nueva partida siempre
        existing = get_all_matches(db)
        match_number = payload.match_number or (len(existing) + 1)
        match = create_match(db, match_number)

        imported_kills = 0
        imported_positions = 0
        errors = []

        for entry in payload.results:
            username = entry.get("username", "").strip()
            kills = int(entry.get("kills", 0) or 0)
            adjustment = int(entry.get("adjustment", 0) or 0)
            position = entry.get("position")

            if not username:
                continue

            try:
                player = get_or_create_player(db, username)
            except Exception as e:
                errors.append(f"No se pudo procesar jugador '{username}': {e}")
                continue

            # Registrar kills como eliminaciones dummy solo si NO hay killfeed detallado
            if not payload.eliminations:
                for k in range(kills):
                    add_elimination(
                        db=db,
                        match_id=match.id,
                        eliminator_username=username,
                        eliminated_username=f"[Rival#{k+1}]",
                        raw_text="[REPLAY_IMPORT]",
                        confidence=1.0,
                    )
                    imported_kills += 1

            # Aplicar ajuste manual para obtener kills efectivas
            effective_kills = max(0, kills + adjustment)

            # Calcular y guardar resultado de posicion para ESTE jugador
            pos = int(position) if position not in (None, "", "null") else None
            place_pts = get_placement_points(pos, player.is_pro) if pos is not None else 0
            kill_pts = get_kill_points(effective_kills, player.is_pro)
            total = place_pts + kill_pts

            upsert_match_result(
                db, match.id, player.id,
                position=pos,
                kills=effective_kills,
                kill_adjustment=adjustment,
                placement_pts=place_pts,
                kill_pts=kill_pts,
                total_pts=total,
            )
            if pos is not None:
                imported_positions += 1

        # ── Insertar killfeed detallado (fuera del loop de jugadores) ────────
        if payload.eliminations:
            for elim in payload.eliminations:
                eliminator = elim.get("eliminator")
                eliminated = elim.get("eliminated")
                weapon = elim.get("weapon")
                time_str = elim.get("time")

                if eliminated:
                    event_tags = elim.get("event_tags")
                    if isinstance(event_tags, list):
                        event_tags = json.dumps(event_tags, ensure_ascii=False)

                    add_elimination(
                        db=db,
                        match_id=match.id,
                        eliminator_username=eliminator,
                        eliminated_username=eliminated,
                        weapon=weapon,
                        match_time=time_str,
                        raw_text="[REPLAY_FEED]",
                        confidence=1.0,
                        gun_type=elim.get("gun_type"),
                        distance=elim.get("distance"),
                        is_self_elimination=bool(elim.get("is_self_elimination", False)),
                        is_npc_elimination=bool(elim.get("is_npc_elimination", False)),
                        is_bot_elimination=bool(elim.get("is_bot_elimination", False)),
                        event_tags=event_tags,
                        display_text=elim.get("display_text"),
                        raw_event_json=elim.get("raw_event_json"),
                    )
                    imported_kills += 1

        standings = build_standings(db)
        return {
            "ok": True,
            "match_id": match.id,
            "match_number": match.match_number,
            "imported_kills": imported_kills,
            "imported_positions": imported_positions,
            "errors": errors,
            "standings": standings,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

