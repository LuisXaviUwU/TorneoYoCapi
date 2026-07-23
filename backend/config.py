"""
config.py — Configuración central del sistema OCR Torneo Fortnite
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


@dataclass
class CaptureRegion:
    top: int = 0
    left: int = 0
    width: int = 600
    height: int = 300


@dataclass
class Config:
    # ── Región de captura del kill feed (pixeles en pantalla) ──────────────
    kill_feed_region: CaptureRegion = field(default_factory=CaptureRegion)

    # ── Sensibilidad de detección de cambios (0-255, menor = más sensible) ─
    change_threshold: float = 3.0

    # ── FPS de captura (recomendado: 5–10) ──────────────────────────────────
    capture_fps: int = 8

    # ── Puerto del servidor ─────────────────────────────────────────────────
    server_host: str = "0.0.0.0"
    server_port: int = int(os.environ.get("PORT", 8000))

    # ── Confianza mínima de OCR para aceptar un resultado (0–1) ────────────
    ocr_min_confidence: float = 0.45

    # ── Idioma del juego ─────────────────────────────────────────────────────
    ocr_languages: list = field(default_factory=lambda: ["es", "en"])

    # ── Tabla de puntos por posición (Casual) ────────────────────────────────
    casual_points: dict = field(default_factory=lambda: {
        1: 42, 2: 35, 3: 30, 4: 26, 5: 23,
        6: 21, 7: 19, 8: 18, 9: 17, 10: 16,
        11: 15, 12: 14, 13: 13, 14: 12, 15: 11,
        16: 3, 17: 3, 18: 3, 19: 3, 20: 3,
        21: 2, 22: 2, 23: 2, 24: 2, 25: 2,
    })

    # ── Tabla de puntos por posición (Pro) ───────────────────────────────────
    pro_points: dict = field(default_factory=lambda: {
        1: 24, 2: 20, 3: 17, 4: 15, 5: 13,
        6: 12, 7: 11, 8: 10, 9: 9, 10: 8,
        11: 7, 12: 6, 13: 5, 14: 4, 15: 3,
        16: 2, 17: 2, 18: 2, 19: 2, 20: 2,
        21: 1, 22: 1, 23: 1, 24: 1, 25: 1,
    })

    # ── Tabla de puntos por posición (legacy, se mantiene por compatibilidad) ─
    placement_points: dict = field(default_factory=lambda: {
        1: 25, 2: 20, 3: 17, 4: 15, 5: 13,
        6: 12, 7: 11, 8: 10, 9: 9,  10: 8,
        11: 7, 12: 6, 13: 5, 14: 4, 15: 3,
        16: 2, 17: 2, 18: 2, 19: 2, 20: 2,
        21: 1, 22: 1, 23: 1, 24: 1, 25: 1,
    })

    # ── Puntos por eliminación ───────────────────────────────────────────────
    kill_points: int = 1  # legacy, unificado
    casual_kill_points: int = 2
    pro_kill_points: int = 1

    # ── Nombre del torneo ────────────────────────────────────────────────────
    tournament_name: str = "Torneo Privado Fortnite"

    # ── Número máximo de partidas ────────────────────────────────────────────
    max_matches: int = 6

    # ── Tiempo mínimo entre eliminaciones detectadas (seg, evita duplicados) ─
    dedup_window_seconds: float = 3.0

    # ── Puntos de bonus para la tabla PRO ────────────────────────────────────
    pro_bonus_points: int = 0


def load_config() -> Config:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = Config()
        region_data = data.pop("kill_feed_region", {})
        cfg.kill_feed_region = CaptureRegion(**region_data)
        for k, v in data.items():
            if hasattr(cfg, k):
                if k in ("casual_points", "pro_points", "placement_points"):
                    v = {int(kk): vv for kk, vv in v.items()}
                setattr(cfg, k, v)
        return cfg
    return Config()


def save_config(cfg: Config) -> None:
    data = asdict(cfg)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Instancia global
config = load_config()
