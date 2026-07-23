"""
scoring_engine.py — Motor de puntuación del torneo.
Aplica la tabla de puntos personalizada y calcula standings.
"""
from typing import Dict, Optional
from .config import config
from .database import (
    Session, get_all_players, get_match_eliminations,
    upsert_match_result, get_player_by_username,
    get_tournament_standings
)


def get_placement_points(position: Optional[int], is_pro: bool = False) -> int:
    """Retorna puntos según posición final y categoría."""
    if position is None or position <= 0:
        return 0
    table = config.pro_points if is_pro else config.casual_points
    pts = table.get(position, 0)
    if is_pro and pts > 0:
        pts += config.pro_bonus_points
    return pts


def get_kill_points(kills: int, is_pro: bool = False) -> int:
    pts = config.pro_kill_points if is_pro else config.casual_kill_points
    return kills * pts


def recalculate_match(db: Session, match_id: int) -> Dict[str, dict]:
    """
    Recalcula los puntos de todos los jugadores en una partida
    basándose en las eliminaciones registradas y posiciones asignadas.
    Retorna un dict {username: {kills, placement_points, kill_points, total_points}}
    """
    from .database import MatchResult
    eliminations = get_match_eliminations(db, match_id)

    # Contar kills por jugador (eliminador)
    # Excluye: autoeliminaciones y eventos de revivir/reboot
    kills_map: Dict[str, int] = {}
    for elim in eliminations:
        if elim.eliminator_username \
                and not elim.is_self_elimination:
            kills_map[elim.eliminator_username] = \
                kills_map.get(elim.eliminator_username, 0) + 1

    # Leer posiciones ya asignadas en MatchResult
    results = db.query(MatchResult).filter(
        MatchResult.match_id == match_id
    ).all()

    summary = {}
    for res in results:
        username = res.player.username
        auto_kills = kills_map.get(username, 0)
        effective_kills = auto_kills + (res.kill_adjustment or 0)
        if effective_kills < 0:
            effective_kills = 0
        place_pts = get_placement_points(res.position, res.player.is_pro)
        kill_pts = get_kill_points(effective_kills, res.player.is_pro)
        bonus_pts = res.bonus_points or 0
        total = place_pts + kill_pts + bonus_pts

        upsert_match_result(
            db, match_id, res.player_id,
            kills=effective_kills,
            placement_pts=place_pts,
            kill_pts=kill_pts,
            bonus_pts=bonus_pts,
            total_pts=total
        )
        summary[username] = {
            "position": res.position,
            "kills": effective_kills,
            "placement_points": place_pts,
            "kill_points": kill_pts,
            "bonus_points": bonus_pts,
            "total_points": total
        }

    return summary


def recalculate_all_matches(db: Session):
    """Recalcula los puntos de todas las partidas registradas."""
    from .database import get_all_matches
    matches = get_all_matches(db)
    for m in matches:
        recalculate_match(db, m.id)


def build_standings(db: Session) -> list:
    """
    Construye la tabla de clasificación completa del torneo.
    Retorna lista de dicts ordenada por total_points DESC.
    """
    rows = get_tournament_standings(db)
    standings = []
    for rank, row in enumerate(rows, start=1):
        standings.append({
            "rank": rank,
            "player_id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "is_pro": bool(row.is_pro),
            "skin_name": row.skin_name if hasattr(row, 'skin_name') else None,
            "total_points": int(row.total_points),
            "total_kills": int(row.total_kills),
            "total_placement_pts": int(row.total_placement_pts),
            "matches_played": int(row.matches_played),
        })
    return standings


def compute_live_kills(db: Session, match_id: int) -> Dict[str, int]:
    """Kills acumulados en la partida activa (excluye autoeliminaciones)."""
    eliminations = get_match_eliminations(db, match_id)
    kills: Dict[str, int] = {}
    for elim in eliminations:
        if elim.eliminator_username \
                and not elim.is_self_elimination:
            kills[elim.eliminator_username] = kills.get(elim.eliminator_username, 0) + 1
    return kills
