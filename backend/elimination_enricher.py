"""
elimination_enricher.py - Convierte eventos crudos del replay en texto de killfeed.

La libreria comunitaria cambia con el formato de Fortnite, asi que este modulo
mantiene la logica defensiva: usa campos finos cuando existen y cae a etiquetas
genericas cuando no.
"""
import json
from typing import Any, Dict, List, Optional


WEAPON_MAP = {
    0: "Tormenta / Caida",
    1: "Explosion",
    2: "Pistola",
    3: "Escopeta",
    4: "Fusil",
    5: "Subfusil",
    6: "Fusil de caza",
    7: "Francotirador",
    8: "Pico",
    9: "Granada / Explosivo",
    10: "Vehiculo",
    11: "Trampa",
    12: "Fuego",
    13: "Caida",
    14: "Objeto arrojadizo",
    15: "Arco",
    16: "Melee",
    17: "Finalizacion / Entorno",
}

NPC_NAME_HINTS = {
    "guardia",
    "jefe",
    "boss",
    "slone",
    "daigo",
    "singularidad",
    "visitante",
    "orden",
    "guardian",
    "bananin",
    "hope",
    "dylan",
    "cluster",
    "cuchilla",
}


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def _first_list(*values: Any) -> List[str]:
    for value in values:
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _contains_tag(tags: List[str], *needles: str) -> bool:
    haystack = " ".join(tags).lower()
    return any(needle.lower() in haystack for needle in needles)


def _looks_like_npc(name: Optional[str], info: Optional[Dict[str, Any]]) -> bool:
    if not name:
        return False

    lowered = name.lower()
    has_npc_name = any(hint in lowered for hint in NPC_NAME_HINTS)
    has_account_id = bool((info or {}).get("Id"))

    # Los NPCs/personajes del mapa suelen venir sin EpicId/BotId real en PlayerData.
    return has_npc_name and not has_account_id


def _format_distance(distance: Any) -> Optional[str]:
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return None

    if value <= 0:
        return None

    return f"{value:.0f} m" if value >= 10 else f"{value:.1f} m"


def enrich_elimination(
    event: Dict[str, Any],
    *,
    eliminator_name: Optional[str],
    eliminated_name: str,
    eliminator_info: Optional[Dict[str, Any]] = None,
    eliminated_info: Optional[Dict[str, Any]] = None,
    killfeed_event: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    gun_type = event.get("GunType")
    weapon = WEAPON_MAP.get(gun_type, f"Arma #{gun_type}")

    tags = _first_list(
        event.get("DeathTags"),
        event.get("Tags"),
        (killfeed_event or {}).get("DeathTags"),
        (killfeed_event or {}).get("Tags"),
    )

    specials: List[str] = []
    if _contains_tag(tags, "HeadShot", "Headshot"):
        specials.append("headshot")
    if _contains_tag(tags, "NoScope", "No_Scope", "NonAds", "HipFire"):
        specials.append("sin apuntar")
    if _contains_tag(tags, "LoggedOut"):
        specials.append("desconexion")

    distance_label = _format_distance(event.get("Distance"))
    if distance_label:
        specials.append(distance_label)

    is_self = bool(event.get("IsSelfElimination"))
    is_npc_target = _looks_like_npc(eliminated_name, eliminated_info)
    is_bot_target = bool((eliminated_info or {}).get("IsBot"))

    if is_npc_target:
        specials.append("NPC/Jefe")

    if not eliminator_name:
        actor = "Tormenta/caida"
    elif is_self:
        actor = eliminator_name
    else:
        actor = eliminator_name

    if is_self:
        display_text = f"{actor} se elimino con {weapon}"
    elif is_npc_target:
        display_text = f"{actor} elimino al jefe/NPC {eliminated_name}"
    else:
        display_text = f"{actor} elimino a {eliminated_name} con {weapon}"

    if specials:
        display_text = f"{display_text} ({', '.join(specials)})"

    return {
        "weapon": weapon,
        "gun_type": gun_type,
        "distance": event.get("Distance"),
        "is_self_elimination": is_self,
        "is_npc_elimination": is_npc_target,
        "is_bot_elimination": is_bot_target,
        "event_tags": tags,
        "display_text": display_text,
        "raw_event_json": _safe_json({
            "elimination": event,
            "killfeed": killfeed_event,
        }),
    }
