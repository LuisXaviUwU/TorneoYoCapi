"""
replay_importer.py - Lee archivos .replay de Fortnite y extrae kills,
posiciones y un killfeed enriquecido.
"""
import glob
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .elimination_enricher import enrich_elimination


FORTNITE_REPLAY_DIR = os.path.expandvars(
    r"%localappdata%\FortniteGame\Saved\Demos"
)
DEBUG_REPLAY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_replays")


def get_latest_replay() -> Optional[str]:
    """Devuelve la ruta del replay mas reciente en la carpeta de Fortnite."""
    if not os.path.exists(FORTNITE_REPLAY_DIR):
        return None
    pattern = os.path.join(FORTNITE_REPLAY_DIR, "**", "*.replay")
    files = glob.glob(pattern, recursive=True)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def list_replays(n: int = 10) -> List[Dict]:
    """Lista los N replays mas recientes."""
    if not os.path.exists(FORTNITE_REPLAY_DIR):
        return []
    pattern = os.path.join(FORTNITE_REPLAY_DIR, "**", "*.replay")
    files = glob.glob(pattern, recursive=True)
    files.sort(key=os.path.getmtime, reverse=True)

    result = []
    for replay_file in files[:n]:
        stat = os.stat(replay_file)
        result.append({
            "path": replay_file,
            "name": os.path.basename(replay_file),
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "modified": stat.st_mtime,
        })
    return result


def _player_ids(player: Dict) -> List[str]:
    ids = []
    for key in ("EpicId", "BotId", "playerId", "Id"):
        value = player.get(key)
        if value is not None:
            ids.append(str(value))
    return ids


def _index_player_maps(raw_players: List[Dict]) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    id_to_name: Dict[str, str] = {}
    id_to_player: Dict[str, Dict] = {}

    for player in raw_players:
        name = player.get("PlayerName")
        if not name:
            continue

        id_to_name[name] = name
        id_to_player[name] = player
        for player_id in _player_ids(player):
            id_to_name[player_id] = name
            id_to_player[player_id] = player

    return id_to_name, id_to_player


def _killfeed_by_start_time(killfeed: List[Dict]) -> Dict[int, Dict]:
    indexed: Dict[int, Dict] = {}
    for event in killfeed or []:
        start = event.get("StartTime") or event.get("Time") or event.get("ServerTime")
        try:
            indexed[int(start)] = event
        except (TypeError, ValueError):
            continue
    return indexed


def _matching_killfeed_event(event: Dict, indexed_killfeed: Dict[int, Dict]) -> Optional[Dict]:
    start = (event.get("Info") or {}).get("StartTime")
    try:
        return indexed_killfeed.get(int(start))
    except (TypeError, ValueError):
        return None


def _write_debug_replay(replay_path: str, data: Dict) -> Optional[str]:
    raw_debug = data.get("rawDebug")
    if not raw_debug:
        return None

    os.makedirs(DEBUG_REPLAY_DIR, exist_ok=True)
    digest = hashlib.sha1(os.path.abspath(replay_path).encode("utf-8", errors="ignore")).hexdigest()[:10]
    filename = f"{Path(replay_path).stem}_{digest}.json"
    debug_path = os.path.join(DEBUG_REPLAY_DIR, filename)
    with open(debug_path, "w", encoding="utf-8") as fh:
        json.dump(raw_debug, fh, ensure_ascii=False, indent=2)
    return debug_path


def _run_node_parser(replay_path: str, debug: bool) -> Dict:
    script_path = os.path.join(os.path.dirname(__file__), "parse_replay_node.js")
    env = os.environ.copy()
    if debug:
        env["REPLAY_INCLUDE_RAW"] = "1"

    res = subprocess.run(
        ["node", script_path, replay_path],
        capture_output=True,
        timeout=120,
        env=env,
    )

    stdout = res.stdout.decode("utf-8", errors="replace").strip() if res.stdout else ""
    stderr = res.stderr.decode("utf-8", errors="replace").strip() if res.stderr else ""

    if not stdout:
        detail = stderr[:500] if stderr else "El script de Node no produjo ninguna salida."
        raise RuntimeError(f"El parser no pudo leer este replay. Detalle: {detail}")

    if res.returncode != 0:
        raise RuntimeError(f"El parser de Node.js fallo (codigo {res.returncode}). {stderr[:300]}")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Respuesta invalida del parser. El archivo puede estar corrupto o no soportado.") from exc


def parse_replay(replay_path: str, known_players: List[str] = None, debug: bool = False) -> Dict:
    """
    Punto de entrada principal. Usa fortnite-replay-analysis desde Node.js y
    normaliza el resultado para el dashboard.
    """
    print(f"[Replay] Analizando con Node.js: {os.path.basename(replay_path)}")

    try:
        data = _run_node_parser(replay_path, debug)

        if not data.get("success"):
            err_msg = data.get("error", "Error desconocido")
            print(f"[Replay] Error en parser: {err_msg}")
            return {"error": err_msg}

        debug_path = _write_debug_replay(replay_path, data) if debug else None

        players_dict = data.get("players", {})
        raw_players = players_dict.get("raw", []) if isinstance(players_dict, dict) else []

        if not raw_players:
            print("[Replay] Parser ejecuto correctamente pero no encontro jugadores.")
            return {
                "error": "El replay no contiene datos de jugadores. Las partidas privadas/personalizadas pueden no ser compatibles."
            }

        kills_map: Dict[str, int] = {}
        placements: Dict[str, int] = {}
        possible_players: List[str] = []

        for player in raw_players:
            name = player.get("PlayerName")
            if not name:
                continue

            epic_id = player.get("EpicId")
            is_bot_flag = player.get("IsBot", False)
            is_true_bot = bool(is_bot_flag and not epic_id)

            if is_true_bot:
                continue

            possible_players.append(name)

            kills = player.get("Kills")
            if kills and kills > 0:
                kills_map[name] = kills

            place = player.get("Placement")
            if place:
                placements[name] = place

        if known_players:
            for known_player in known_players:
                if known_player not in possible_players:
                    possible_players.append(known_player)

        id_to_name, id_to_player = _index_player_maps(raw_players)
        indexed_killfeed = _killfeed_by_start_time(data.get("killFeed", []))

        parsed_elims = []
        for event in data.get("eliminations", []):
            if event.get("Knocked") is True:
                continue

            eliminator_id = event.get("Eliminator")
            eliminated_id = event.get("Eliminated")
            time_str = event.get("Time")

            eliminator_key = str(eliminator_id) if eliminator_id is not None else None
            eliminated_key = str(eliminated_id) if eliminated_id is not None else None
            eliminator_name = id_to_name.get(eliminator_key) if eliminator_key else None
            eliminated_name = id_to_name.get(eliminated_key) if eliminated_key else None

            if not eliminated_name:
                continue

            killfeed_event = _matching_killfeed_event(event, indexed_killfeed)
            enriched = enrich_elimination(
                event,
                eliminator_name=eliminator_name,
                eliminated_name=eliminated_name,
                eliminator_info=id_to_player.get(eliminator_key) if eliminator_key else None,
                eliminated_info=id_to_player.get(eliminated_key) if eliminated_key else None,
                killfeed_event=killfeed_event,
            )

            parsed_elims.append({
                "eliminator": eliminator_name,
                "eliminated": eliminated_name,
                "weapon": enriched["weapon"],
                "gun_type": enriched["gun_type"],
                "distance": enriched["distance"],
                "is_self_elimination": enriched["is_self_elimination"],
                "is_npc_elimination": enriched["is_npc_elimination"],
                "is_bot_elimination": enriched["is_bot_elimination"],
                "event_tags": enriched["event_tags"],
                "display_text": enriched["display_text"],
                "raw_event_json": enriched["raw_event_json"],
                "time": time_str,
                "knocked": False,
            })

        print(
            "[Replay] OK: "
            f"{len(possible_players)} jugadores reales, "
            f"{len(kills_map)} con kills, "
            f"{len(placements)} con posicion, "
            f"{len(parsed_elims)} eliminaciones."
        )

        return {
            "source": "nodejs_parser",
            "possible_players": sorted(possible_players),
            "kills": kills_map,
            "placements": placements,
            "eliminations": parsed_elims,
            "debug": data.get("debug", {}),
            "debug_export": debug_path,
        }

    except subprocess.TimeoutExpired:
        print("[Replay] Node.js tardo demasiado (>120s).")
        return {"error": "El parser tardo demasiado. El archivo puede ser muy grande o estar danado."}
    except Exception as exc:
        print(f"[Replay] Excepcion fatal: {exc}")
        return {"error": str(exc)}
