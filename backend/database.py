"""
database.py — Modelos y operaciones de base de datos (SQLite + SQLAlchemy)
"""
import os
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, UniqueConstraint, func, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "tournament.db")
# Read from environment, fallback to SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# For PostgreSQL (Render/Supabase), connect_args is different
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─────────────────────────── MODELOS ───────────────────────────────────────

class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    is_pro = Column(Boolean, default=False)
    role = Column(String, nullable=True)  # Ej: 'Organizadora', 'Coordinador'
    skin_name = Column(String, nullable=True)  # Nombre de la skin de Fortnite para el avatar
    registered_at = Column(DateTime, default=datetime.utcnow)

    eliminations_made = relationship(
        "Elimination", foreign_keys="Elimination.eliminator_username",
        primaryjoin="Player.username == Elimination.eliminator_username",
        backref="eliminator_player"
    )


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    match_number = Column(Integer, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    eliminations = relationship("Elimination", back_populates="match")
    results = relationship("MatchResult", back_populates="match")


class Elimination(Base):
    __tablename__ = "eliminations"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    eliminator_username = Column(String, nullable=True)   # Null = caída al vacío
    eliminated_username = Column(String, nullable=False)
    weapon = Column(String, nullable=True)
    gun_type = Column(Integer, nullable=True)
    distance = Column(Float, nullable=True)
    is_self_elimination = Column(Boolean, default=False)
    is_npc_elimination = Column(Boolean, default=False)
    is_bot_elimination = Column(Boolean, default=False)
    event_tags = Column(Text, nullable=True)
    display_text = Column(Text, nullable=True)
    raw_event_json = Column(Text, nullable=True)
    match_time = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    raw_text = Column(String, nullable=True)
    confidence = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)
    is_corrected = Column(Boolean, default=False)

    match = relationship("Match", back_populates="eliminations")


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    position = Column(Integer, nullable=True)
    kills = Column(Integer, default=0)
    kill_adjustment = Column(Integer, default=0)
    bonus_points = Column(Integer, default=0)
    placement_points = Column(Integer, default=0)
    kill_points = Column(Integer, default=0)
    total_points = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    match = relationship("Match", back_populates="results")
    player = relationship("Player")


# ─────────────────────────── HELPERS ───────────────────────────────────────

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    migrations = [
        ("players", "role", "TEXT"),
        ("eliminations", "gun_type", "INTEGER"),
        ("eliminations", "distance", "FLOAT"),
        ("eliminations", "is_self_elimination", "BOOLEAN DEFAULT 0"),
        ("eliminations", "is_npc_elimination", "BOOLEAN DEFAULT 0"),
        ("eliminations", "is_bot_elimination", "BOOLEAN DEFAULT 0"),
        ("eliminations", "event_tags", "TEXT"),
        ("eliminations", "display_text", "TEXT"),
        ("eliminations", "raw_event_json", "TEXT"),
        ("match_results", "kill_adjustment", "INTEGER DEFAULT 0"),
        ("match_results", "bonus_points", "INTEGER DEFAULT 0"),
        ("players", "skin_name", "TEXT"),
    ]
    with engine.connect() as conn:
        for table, column, definition in migrations:
            try:
                conn.execute(__import__('sqlalchemy').text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                ))
                conn.commit()
            except Exception:
                pass


# ─── Player helpers ────────────────────────────────────────────────────────

def get_all_players(db: Session) -> List[Player]:
    return db.query(Player).order_by(Player.username).all()


def get_player_by_username(db: Session, username: str) -> Optional[Player]:
    """Busca un jugador por username, insensible a mayúsculas para cualquier idioma (Unicode)."""
    username_clean = username.strip()
    # Intento exacto primero (más rápido)
    player = db.query(Player).filter(Player.username == username_clean).first()
    if player:
        return player
    # Fallback: comparación Python (soporta cirílico, japonés, árabe, etc.)
    username_lower = username_clean.lower()
    all_players = db.query(Player).all()
    for p in all_players:
        if p.username.lower() == username_lower:
            return p
    return None


def create_player(db: Session, username: str, display_name: str = None, is_pro: bool = False) -> Player:
    player = Player(username=username.strip(), display_name=display_name, is_pro=is_pro)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def delete_player(db: Session, player_id: int) -> bool:
    player = db.query(Player).filter(Player.id == player_id).first()
    if player:
        db.delete(player)
        db.commit()
        return True
    return False


def set_player_role(db: Session, player_id: int, role: Optional[str]) -> Optional[Player]:
    """Asigna o limpia el rol especial de un jugador (Organizadora, Coordinador, etc.)."""
    player = db.query(Player).filter(Player.id == player_id).first()
    if player:
        player.role = role if role else None
        db.commit()
        db.refresh(player)
    return player


# ─── Match helpers ─────────────────────────────────────────────────────────

def get_active_match(db: Session) -> Optional[Match]:
    return db.query(Match).filter(Match.is_active == True).first()


def get_all_matches(db: Session) -> List[Match]:
    return db.query(Match).order_by(Match.match_number).all()


def create_match(db: Session, match_number: int) -> Match:
    match = Match(match_number=match_number)
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def end_match(db: Session, match_id: int) -> Optional[Match]:
    match = db.query(Match).filter(Match.id == match_id).first()
    if match:
        match.is_active = False
        match.ended_at = datetime.utcnow()
        db.commit()
        db.refresh(match)
    return match


def delete_match(db: Session, match_id: int) -> bool:
    match = db.query(Match).filter(Match.id == match_id).first()
    if match:
        # Delete related eliminations and results manually if not cascade
        db.query(Elimination).filter(Elimination.match_id == match_id).delete()
        db.query(MatchResult).filter(MatchResult.match_id == match_id).delete()
        db.delete(match)
        db.commit()
        return True
    return False


# ─── Elimination helpers ───────────────────────────────────────────────────

def add_elimination(
    db: Session, match_id: int,
    eliminator_username: Optional[str],
    eliminated_username: str,
    weapon: Optional[str] = None,
    match_time: Optional[str] = None,
    raw_text: str = "",
    confidence: float = 0.0,
    gun_type: Optional[int] = None,
    distance: Optional[float] = None,
    is_self_elimination: bool = False,
    is_npc_elimination: bool = False,
    is_bot_elimination: bool = False,
    event_tags: Optional[str] = None,
    display_text: Optional[str] = None,
    raw_event_json: Optional[str] = None,
) -> Elimination:
    elim = Elimination(
        match_id=match_id,
        eliminator_username=eliminator_username,
        eliminated_username=eliminated_username,
        weapon=weapon,
        gun_type=gun_type,
        distance=distance,
        is_self_elimination=is_self_elimination,
        is_npc_elimination=is_npc_elimination,
        is_bot_elimination=is_bot_elimination,
        event_tags=event_tags,
        display_text=display_text,
        raw_event_json=raw_event_json,
        match_time=match_time,
        raw_text=raw_text,
        confidence=confidence
    )
    db.add(elim)
    db.commit()
    db.refresh(elim)
    return elim


def get_match_eliminations(db: Session, match_id: int) -> List[Elimination]:
    return db.query(Elimination).filter(
        Elimination.match_id == match_id
    ).order_by(Elimination.timestamp).all()


def correct_elimination(
    db: Session, elim_id: int,
    eliminator_username: Optional[str] = None,
    eliminated_username: Optional[str] = None
) -> Optional[Elimination]:
    elim = db.query(Elimination).filter(Elimination.id == elim_id).first()
    if elim:
        if eliminator_username is not None:
            elim.eliminator_username = eliminator_username
        if eliminated_username is not None:
            elim.eliminated_username = eliminated_username
        elim.is_corrected = True
        elim.is_verified = True
        db.commit()
        db.refresh(elim)
    return elim


def delete_elimination(db: Session, elim_id: int) -> bool:
    elim = db.query(Elimination).filter(Elimination.id == elim_id).first()
    if elim:
        db.delete(elim)
        db.commit()
        return True
    return False


# ─── MatchResult helpers ───────────────────────────────────────────────────

def upsert_match_result(
    db: Session, match_id: int, player_id: int,
    position: Optional[int] = None,
    kills: Optional[int] = None,
    kill_adjustment: Optional[int] = None,
    bonus_pts: Optional[int] = None,
    placement_pts: Optional[int] = None,
    kill_pts: Optional[int] = None,
    total_pts: Optional[int] = None
) -> MatchResult:
    result = db.query(MatchResult).filter(
        MatchResult.match_id == match_id,
        MatchResult.player_id == player_id
    ).first()

    if not result:
        result = MatchResult(match_id=match_id, player_id=player_id)
        db.add(result)

    if position is not None:
        result.position = position
    if kills is not None:
        result.kills = kills
    if kill_adjustment is not None:
        result.kill_adjustment = kill_adjustment
    if bonus_pts is not None:
        result.bonus_points = bonus_pts
    if placement_pts is not None:
        result.placement_points = placement_pts
    if kill_pts is not None:
        result.kill_points = kill_pts
    if total_pts is not None:
        result.total_points = total_pts

    db.commit()
    db.refresh(result)
    return result


def get_match_results(db: Session, match_id: int):
    """Retorna la clasificación de una partida específica."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT
            p.id,
            p.username,
            COALESCE(p.display_name, p.username) AS display_name,
            p.is_pro,
            mr.position,
            mr.kills,
            mr.kill_adjustment,
            mr.bonus_points,
            mr.placement_points,
            mr.kill_points,
            mr.total_points
        FROM match_results mr
        JOIN players p ON mr.player_id = p.id
        WHERE mr.match_id = :match_id
        ORDER BY mr.total_points DESC, mr.kills DESC
    """), {"match_id": match_id}).fetchall()
    return rows


def get_tournament_standings(db: Session):
    """Retorna la clasificación total del torneo (suma de todas las partidas).
    Solo incluye jugadores que han jugado al menos una partida.
    """
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT
            p.id,
            p.username,
            COALESCE(p.display_name, p.username) AS display_name,
            p.is_pro,
            p.skin_name,
            COALESCE(SUM(mr.total_points), 0) AS total_points,
            COALESCE(SUM(mr.kills), 0) AS total_kills,
            COALESCE(SUM(mr.placement_points), 0) AS total_placement_pts,
            COUNT(mr.id) AS matches_played
        FROM players p
        INNER JOIN match_results mr ON mr.player_id = p.id
        GROUP BY p.id
        HAVING COUNT(mr.id) > 0
        ORDER BY total_points DESC, total_kills DESC
    """)).fetchall()
    return rows
