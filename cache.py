#cache.py
import logging
import os
import sqlite3
import threading
import time
import json
from datetime import datetime

logger = logging.getLogger(__name__)

from config import (
    DB_PATH, DAYS_CONSIDERED_NEW, NEW_CACHE_DURATION, OLD_CACHE_DURATION,
    TRENDING_CACHE_DURATION, TMDB_POSTER_CACHE_DIR, TMDB_POSTER_CACHE_DURATION,
    TMDB_LOGO_CACHE_DIR, TMDB_LOGO_CACHE_DURATION, TMDB_METADATA_CACHE_DURATION,
    COMPOSITE_CACHE_TTL, COMPOSITE_MAX_ENTRIES, QUALITY_OLD_CACHE_DURATION,
    DIGITAL_RELEASE_MAX_AGE_DAYS, COMPOSITE_CACHE_DIR
)

_db_conn: sqlite3.Connection | None = None
_db_lock = threading.Lock()

def get_db() -> sqlite3.Connection:
    if _db_conn is None: raise RuntimeError("Database not initialized")
    return _db_conn

def init_db() -> None:
    global _db_conn
    os.makedirs(TMDB_POSTER_CACHE_DIR, exist_ok=True)
    os.makedirs(TMDB_LOGO_CACHE_DIR, exist_ok=True)
    # NUOVO: Creiamo la directory fisica per i poster composti
    os.makedirs(COMPOSITE_CACHE_DIR, exist_ok=True)
    
    _db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _db_conn.execute("PRAGMA journal_mode=WAL")
    _db_conn.execute("PRAGMA synchronous=NORMAL")
    _db_conn.execute("PRAGMA cache_size=-32000")
    _db_conn.execute("PRAGMA temp_store=MEMORY")
    _db_conn.execute("PRAGMA busy_timeout=5000")
    _db_conn.execute("PRAGMA wal_autocheckpoint=1000")

    # NUOVO: Pulizia automatica della vecchia tabella BLOB se si proviene dalla v4
    _db_conn.execute("DROP TABLE IF EXISTS final_poster_cache")

    _db_conn.execute("""
    CREATE TABLE IF NOT EXISTS rating_cache (
        imdb_id TEXT PRIMARY KEY, ratings_json TEXT, genre TEXT, cached_at INTEGER,
        release_date TEXT, award_wins TEXT, award_noms TEXT, awards_fetched INTEGER NOT NULL DEFAULT 0,
        festival_label TEXT, age_rating INTEGER, is_cult INTEGER NOT NULL DEFAULT 0,
        is_true_story INTEGER NOT NULL DEFAULT 0, is_metacritic INTEGER NOT NULL DEFAULT 0
    )""")

    existing_cols = {row[1] for row in _db_conn.execute("PRAGMA table_info(rating_cache)").fetchall()}
    for col, definition in (
        ("award_wins", "TEXT NOT NULL DEFAULT ''"), ("award_noms", "TEXT NOT NULL DEFAULT ''"),
        ("awards_fetched", "INTEGER NOT NULL DEFAULT 0"), ("festival_label", "TEXT"), ("age_rating", "INTEGER"),
        ("is_cult", "INTEGER NOT NULL DEFAULT 0"), ("is_true_story", "INTEGER NOT NULL DEFAULT 0"),
        ("is_metacritic", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in existing_cols: _db_conn.execute(f"ALTER TABLE rating_cache ADD COLUMN {col} {definition}")

    _db_conn.execute("""CREATE TABLE IF NOT EXISTS quality_cache (imdb_id TEXT PRIMARY KEY, tokens TEXT, cached_at INTEGER, release_date TEXT)""")
    _db_conn.execute("""CREATE TABLE IF NOT EXISTS trending_cache (media_type TEXT PRIMARY KEY, rankings_json TEXT, cached_at INTEGER)""")
    
    # AOD and System Meta Tables
    _db_conn.execute("""CREATE TABLE IF NOT EXISTS aod_cache (kitsu_id TEXT PRIMARY KEY, tmdb_id TEXT, media_type TEXT)""")
    _db_conn.execute("""CREATE TABLE IF NOT EXISTS sys_meta (key TEXT PRIMARY KEY, val TEXT)""")

    _db_conn.execute("""
        CREATE TABLE IF NOT EXISTS tmdb_metadata_cache (
            cache_key TEXT PRIMARY KEY, title TEXT, release_year TEXT, genre_ids TEXT, is_textless INTEGER,
            poster_path TEXT, logos_json TEXT, cached_at INTEGER, credits_json TEXT, production_cos_json TEXT,
            runtime INTEGER, number_of_seasons INTEGER, number_of_episodes INTEGER, original_language TEXT, backdrop_path TEXT,
            status TEXT, next_episode_to_air TEXT
        )
    """)

    _db_conn.execute("""CREATE TABLE IF NOT EXISTS digital_release_cache (imdb_id TEXT PRIMARY KEY, posted_at INTEGER NOT NULL)""")

    existing_meta_cols = {row[1] for row in _db_conn.execute("PRAGMA table_info(tmdb_metadata_cache)").fetchall()}
    for col, definition in (
        ("credits_json", "TEXT"), ("production_cos_json", "TEXT"), ("runtime", "INTEGER"),
        ("number_of_seasons", "INTEGER"), ("number_of_episodes", "INTEGER"), ("original_language", "TEXT"),
        ("backdrop_path", "TEXT"), ("status", "TEXT"), ("next_episode_to_air", "TEXT")
    ):
        if col not in existing_meta_cols: _db_conn.execute(f"ALTER TABLE tmdb_metadata_cache ADD COLUMN {col} {definition}")

    _db_conn.commit()

# --- AOD HELPERS ---
def get_aod_mapping(provider_id: str):
    try:
        row = get_db().execute("SELECT tmdb_id, media_type FROM aod_cache WHERE kitsu_id = ?", (provider_id,)).fetchone()
        # Fallback per evitare rotture con salvataggi precedenti
        if not row and provider_id.startswith("kitsu_"):
            legacy_id = provider_id.replace("kitsu_", "")
            row = get_db().execute("SELECT tmdb_id, media_type FROM aod_cache WHERE kitsu_id = ?", (legacy_id,)).fetchone()
        return row if row else None
    except Exception: return None

def update_aod_mapping(mappings: list[tuple[str, str, str]]):
    try:
        with _db_lock:
            get_db().executemany("INSERT OR REPLACE INTO aod_cache (kitsu_id, tmdb_id, media_type) VALUES (?, ?, ?)", mappings)
            get_db().commit()
    except Exception as exc: logger.error(f"AOD cache write error: {exc}")
# -------------------

def get_sys_meta(key: str):
    try:
        row = get_db().execute("SELECT val FROM sys_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    except Exception: return None

def set_sys_meta(key: str, val: str):
    try:
        with _db_lock:
            get_db().execute("INSERT OR REPLACE INTO sys_meta (key, val) VALUES (?, ?)", (key, val))
            get_db().commit()
    except Exception: pass
# -------------------

def _rating_ttl(release_date: str | None) -> int:
    if not release_date: return OLD_CACHE_DURATION
    try:
        days_since = (datetime.now() - datetime.strptime(release_date, "%Y-%m-%d")).days
        return NEW_CACHE_DURATION if days_since <= DAYS_CONSIDERED_NEW else OLD_CACHE_DURATION
    except ValueError: return OLD_CACHE_DURATION

def _quality_ttl(release_date: str | None) -> int:
    if not release_date: return QUALITY_OLD_CACHE_DURATION
    try:
        days_since = (datetime.now() - datetime.strptime(release_date, "%Y-%m-%d")).days
        return NEW_CACHE_DURATION if days_since <= DAYS_CONSIDERED_NEW else QUALITY_OLD_CACHE_DURATION
    except ValueError: return QUALITY_OLD_CACHE_DURATION


# NUOVO: Helper per pulire i nomi dei file (i due punti ":" non piacciono ad alcuni OS)
def _get_composite_path(cache_key: str) -> str:
    safe_key = cache_key.replace(":", "_") + ".jpg"
    return os.path.realpath(os.path.join(COMPOSITE_CACHE_DIR, safe_key))

# NUOVO: Lettura da File System invece che da SQLite
def get_cached_final_poster(cache_key: str) -> bytes | None:
    path = _get_composite_path(cache_key)
    if not os.path.exists(path): return None
    if (time.time() - os.path.getmtime(path)) > COMPOSITE_CACHE_TTL:
        try: os.remove(path)
        except FileNotFoundError: pass
        return None
    try:
        with open(path, "rb") as f: return f.read()
    except Exception: return None

# NUOVO: Scrittura su File System e gestione della capienza massima
def set_cached_final_poster(cache_key: str, jpeg_bytes: bytes) -> None:
    try:
        path = _get_composite_path(cache_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f: f.write(jpeg_bytes)
        
        # Gestione del COMPOSITE_MAX_ENTRIES limitando il numero di file
        if COMPOSITE_MAX_ENTRIES > 0:
            files = [os.path.join(COMPOSITE_CACHE_DIR, f) for f in os.listdir(COMPOSITE_CACHE_DIR) if f.endswith('.jpg')]
            if len(files) > COMPOSITE_MAX_ENTRIES:
                files.sort(key=os.path.getmtime) # Ordina dal più vecchio al più nuovo
                overflow = len(files) - COMPOSITE_MAX_ENTRIES
                for f in files[:overflow]:
                    try: os.remove(f)
                    except OSError: pass
    except Exception: pass

def prune_caches() -> None:
    now = int(time.time())
    try:
        # Pulisce i dati testuali su SQLite
        with _db_lock:
            db = get_db()
            db.execute("DELETE FROM rating_cache WHERE cached_at < ?", (now - OLD_CACHE_DURATION * 86400,))
            db.execute("DELETE FROM quality_cache WHERE cached_at < ?", (now - QUALITY_OLD_CACHE_DURATION * 86400,))
            db.execute("DELETE FROM tmdb_metadata_cache WHERE cached_at < ?", (now - TMDB_METADATA_CACHE_DURATION * 86400,))
            db.execute("DELETE FROM digital_release_cache WHERE posted_at < ?", (now - DIGITAL_RELEASE_MAX_AGE_DAYS * 86400,))
            db.commit()
        with _db_lock:
            get_db().execute("PRAGMA incremental_vacuum(100)")
            get_db().commit()
            
        # NUOVO: Pulisce le vecchie immagini fisiche dal disco
        for f in os.listdir(COMPOSITE_CACHE_DIR):
            p = os.path.join(COMPOSITE_CACHE_DIR, f)
            if os.path.isfile(p) and (now - os.path.getmtime(p)) > COMPOSITE_CACHE_TTL:
                try: os.remove(p)
                except OSError: pass
    except Exception: pass

def get_cached_rating(imdb_id: str):
    try:
        row = get_db().execute("SELECT ratings_json, genre, cached_at, release_date, award_wins, award_noms, awards_fetched, festival_label, age_rating, is_cult, is_true_story, is_metacritic FROM rating_cache WHERE imdb_id = ?", (imdb_id,)).fetchone()
        if not row: return None
        (ratings_json, genre, cached_at, release_date, wins_raw, noms_raw, awards_fetched_int, festival_label, age_rating, is_cult_int, is_true_story_int, is_metacritic_int) = row
        if (time.time() - cached_at) / 86400 > _rating_ttl(release_date):
            with _db_lock:
                get_db().execute("DELETE FROM rating_cache WHERE imdb_id = ?", (imdb_id,))
                get_db().commit()
            return None
        return (json.loads(ratings_json or "{}"), genre, release_date, [w for w in (wins_raw or "").split("|") if w], [n for n in (noms_raw or "").split("|") if n], bool(awards_fetched_int), festival_label, age_rating, bool(is_cult_int), bool(is_true_story_int), bool(is_metacritic_int))
    except Exception: return None

def set_cached_rating(imdb_id: str, ratings_dict: dict, genre: str, rel: str | None, award_wins: list[str], award_noms: list[str], awards_fetched: bool = False, festival_label: str | None = None, age_rating: int | None = None, is_cult: bool = False, is_true_story: bool = False, is_metacritic: bool = False) -> None:
    try:
        with _db_lock:
            get_db().execute("INSERT OR REPLACE INTO rating_cache (imdb_id, ratings_json, genre, cached_at, release_date, award_wins, award_noms, awards_fetched, festival_label, age_rating, is_cult, is_true_story, is_metacritic) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (imdb_id, json.dumps(ratings_dict), genre, int(time.time()), rel, "|".join(award_wins or []), "|".join(award_noms or []), int(awards_fetched), festival_label, age_rating, int(is_cult), int(is_true_story), int(is_metacritic)))
            get_db().commit()
    except Exception: pass

def get_cached_trending_snapshot(media_type: str) -> dict[str, int] | None:
    try:
        row = get_db().execute("SELECT rankings_json, cached_at FROM trending_cache WHERE media_type = ?", (media_type,)).fetchone()
        if not row: return None
        if (time.time() - row[1]) / 86400 > TRENDING_CACHE_DURATION: return None
        return json.loads(row[0])
    except Exception: return None

def set_cached_trending_snapshot(media_type: str, rankings: dict[str, int]) -> None:
    try:
        with _db_lock:
            get_db().execute("INSERT OR REPLACE INTO trending_cache (media_type, rankings_json, cached_at) VALUES (?, ?, ?)", (media_type, json.dumps(rankings), int(time.time())))
            get_db().commit()
    except Exception: pass

def _safe_cache_path(base_dir: str, filename: str) -> str:
    path = os.path.realpath(os.path.join(base_dir, filename))
    if not path.startswith(os.path.realpath(base_dir)): raise ValueError("Path traversal attempt")
    return path        

def get_cached_tmdb_poster(cache_key: str) -> bytes | None:
    path = _safe_cache_path(TMDB_POSTER_CACHE_DIR, cache_key)
    if not os.path.exists(path): return None
    if (time.time() - os.path.getmtime(path)) / 86400 > TMDB_POSTER_CACHE_DURATION:
        try: os.remove(path)
        except FileNotFoundError: pass
        return None
    try:
        with open(path, "rb") as f: return f.read()
    except Exception: return None

def set_cached_tmdb_poster(cache_key: str, data: bytes) -> None:
    try:
        path = _safe_cache_path(TMDB_POSTER_CACHE_DIR, cache_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f: f.write(data)
    except Exception: pass

def _remove_if_dir(path: str) -> bool:
    if os.path.isdir(path):
        try: os.rmdir(path)
        except OSError: pass
        return True
    return False

def get_cached_tmdb_logo(cache_key: str) -> bytes | None:
    path = _safe_cache_path(TMDB_LOGO_CACHE_DIR, cache_key)
    if _remove_if_dir(path) or not os.path.exists(path): return None
    if (time.time() - os.path.getmtime(path)) / 86400 > TMDB_LOGO_CACHE_DURATION:
        try: os.remove(path)
        except FileNotFoundError: pass
        return None
    try:
        with open(path, "rb") as f: return f.read()
    except Exception: return None

def set_cached_tmdb_logo(cache_key: str, data: bytes) -> None:
    try:
        path = _safe_cache_path(TMDB_LOGO_CACHE_DIR, cache_key)
        _remove_if_dir(path)
        with open(path, "wb") as f: f.write(data)
    except Exception: pass

def get_cached_tmdb_metadata(cache_key: str) -> dict | None:
    try:
        row = get_db().execute("SELECT title, release_year, genre_ids, is_textless, poster_path, logos_json, cached_at, credits_json, production_cos_json, runtime, number_of_seasons, number_of_episodes, original_language, backdrop_path, status, next_episode_to_air FROM tmdb_metadata_cache WHERE cache_key = ?", (cache_key,)).fetchone()
        if not row: return None
        (title, release_year, genre_ids_raw, is_textless, poster_path, logos_json, cached_at, credits_json, production_cos_json, runtime, number_of_seasons, number_of_episodes, original_language, backdrop_path, status, next_episode_to_air) = row
        if (time.time() - cached_at) / 86400 > TMDB_METADATA_CACHE_DURATION:
            with _db_lock:
                get_db().execute("DELETE FROM tmdb_metadata_cache WHERE cache_key = ?", (cache_key,))
                get_db().commit()
            return None
        return {
            "title": title, "release_year": release_year, "genre_ids": json.loads(genre_ids_raw or "[]"),
            "is_textless": bool(is_textless), "poster_path": poster_path, "logos": json.loads(logos_json or "[]"),
            "credits": json.loads(credits_json or "{}"), "production_companies": json.loads(production_cos_json or "[]"),
            "runtime": runtime, "number_of_seasons": number_of_seasons, "number_of_episodes": number_of_episodes,
            "original_language": original_language, "backdrop_path": backdrop_path,
            "status": status, "next_episode_to_air": next_episode_to_air
        }
    except Exception: return None

def set_cached_tmdb_metadata(
    cache_key: str, title: str, release_year: str | None, genre_ids: list[int], is_textless: bool, poster_path: str, logos: list[dict],
    *, credits: dict | None = None, production_companies: list[dict] | None = None, original_language: str | None = None,
    runtime: int | None = None, number_of_seasons: int | None = None, number_of_episodes: int | None = None, backdrop_path: str | None = None,
    status: str | None = None, next_episode_to_air: str | None = None
) -> None:
    try:
        with _db_lock:
            get_db().execute("""INSERT OR REPLACE INTO tmdb_metadata_cache (cache_key, title, release_year, genre_ids, is_textless, poster_path, logos_json, cached_at, credits_json, production_cos_json, runtime, number_of_seasons, number_of_episodes, original_language, backdrop_path, status, next_episode_to_air) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (cache_key, title, release_year, json.dumps(genre_ids), int(is_textless), poster_path, json.dumps(logos), int(time.time()), json.dumps(credits or {}), json.dumps(production_companies or []), runtime, number_of_seasons, number_of_episodes, original_language, backdrop_path, status, next_episode_to_air))
            get_db().commit()
    except Exception: pass

def delete_cached_tmdb_metadata(cache_key: str) -> None:
    try:
        with _db_lock:
            get_db().execute("DELETE FROM tmdb_metadata_cache WHERE cache_key = ?", (cache_key,))
            get_db().commit()
    except Exception: pass

def is_digital_release(imdb_id: str) -> bool:
    try: return get_db().execute("SELECT 1 FROM digital_release_cache WHERE imdb_id = ?", (imdb_id,)).fetchone() is not None
    except Exception: return False

def count_digital_releases() -> int:
    try: return get_db().execute("SELECT COUNT(*) FROM digital_release_cache").fetchone()[0]
    except Exception: return 0

def add_digital_releases(entries: list[tuple[str, int]]) -> int:
    if not entries: return 0
    inserted = 0
    try:
        with _db_lock:
            for imdb_id, posted_at in entries:
                r = get_db().execute("INSERT OR IGNORE INTO digital_release_cache (imdb_id, posted_at) VALUES (?, ?)", (imdb_id, posted_at))
                inserted += r.rowcount
            get_db().commit()
    except Exception: pass
    return inserted

def get_cached_quality(imdb_id: str, release_date: str | None) -> list[str] | None:
    try:
        row = get_db().execute("SELECT tokens, cached_at FROM quality_cache WHERE imdb_id = ?", (imdb_id,)).fetchone()
        if not row: return None
        tokens_raw, cached_at = row
        if (time.time() - cached_at) / 86400 > _quality_ttl(release_date):
            with _db_lock:
                get_db().execute("DELETE FROM quality_cache WHERE imdb_id = ?", (imdb_id,))
                get_db().commit()
            return None
        return json.loads(tokens_raw or "[]")
    except Exception: return None

def set_cached_quality(imdb_id: str, tokens: list[str], release_date: str | None) -> None:
    try:
        with _db_lock:
            get_db().execute("INSERT OR REPLACE INTO quality_cache (imdb_id, tokens, cached_at, release_date) VALUES (?, ?, ?, ?)", (imdb_id, json.dumps(tokens), int(time.time()), release_date))
            get_db().commit()
    except Exception: pass
