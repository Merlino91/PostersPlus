#config.py
import os
import json

# Storage
DB_PATH               = "/app/cache/cache.db"
BADGE_DIR             = "/app/badges"
TMDB_POSTER_CACHE_DIR = "/app/cache/tmdb_posters"
TMDB_LOGO_CACHE_DIR   = "/app/cache/tmdb_logos"
# NUOVO: Directory per salvare i poster finali su disco invece che in SQLite
COMPOSITE_CACHE_DIR   = "/app/cache/composites" 

# Environment
ACCESS_KEY            = os.environ.get("ACCESS_KEY")
AIOSTREAMS_URL        = os.environ.get("AIOSTREAMS_URL", "")
AIOSTREAMS_AUTH       = os.environ.get("AIOSTREAMS_AUTH", "")
SERVER_TMDB_KEY       = os.environ.get("TMDB_API_KEY", "").strip()
SERVER_FANART_KEY     = os.environ.get("FANART_API_KEY", "").strip()

# NUOVO: Gestione array di chiavi MDBList (supporta fallback per compatibilità)
_mdblist_keys_raw     = os.environ.get("MDBLIST_API_KEYS", os.environ.get("MDBLIST_API_KEY", ""))
SERVER_MDBLIST_KEYS   = [k.strip() for k in _mdblist_keys_raw.split(",") if k.strip()]

# AOD
AOD_URL               = "https://raw.githubusercontent.com/manami-project/anime-offline-database/master/anime-offline-database-minified.json"

# Workers
CDN_CACHE_TTL         = int(os.environ.get("CDN_CACHE_TTL", "0"))
JPEG_QUALITY          = max(70, min(95, int(os.environ.get("JPEG_QUALITY", "85"))))

# Feature Defaults 
SHOW_RATING_DISPLAY_MODE = 1
SHOW_AWARD_SASH          = True
BADGE_DISPLAY_MODE       = 4

# Poster Dimensions (500x750)
POSTER_WIDTH  = 500
POSTER_HEIGHT = 750

# Rating & Genre Label Defaults
ACCENT_BAR_MODE_FONT_SIZE_RATIO    = 0.08
NUMERIC_SCORE_MODE_FONT_SIZE_RATIO = 0.10
MINIMALIST_MODE_FONT_SIZE_RATIO    = 0.055
ACCENT_BAR_MODE_FONT_Y_OFFSET      = 0.90
NUMERIC_SCORE_MODE_FONT_Y_OFFSET   = 0.90
MINIMALIST_MODE_FONT_X_OFFSET      = 0.05
MINIMALIST_MODE_FONT_Y_OFFSET      = 0.92

SCORE_GLOW_THRESHOLD = 85
SCORE_GLOW_BLUR      = 1
SCORE_GLOW_ALPHA     = 40

# Logo Defaults
LOGO_MAX_W_RATIO  = 0.84
LOGO_MAX_H_RATIO  = 0.17
LOGO_BOTTOM_RATIO = 0.28
# NUOVO: Allineato alla UI per usare l'italiano di default
DEFAULT_LOGO_LANGUAGE = os.environ.get("DEFAULT_LOGO_LANGUAGE", "it")

# Quality Badge Defaults
BADGE_HEIGHT = 20
BADGE_GAP    = 8
BADGE_ANCHOR_X_RATIO = 0.050
BADGE_ANCHOR_Y_RATIO = 0.050

# TTL Settings
TMDB_POSTER_CACHE_DURATION   = 60
TMDB_LOGO_CACHE_DURATION     = 60
TMDB_METADATA_CACHE_DURATION = 7
DAYS_CONSIDERED_NEW          = 14
NEW_CACHE_DURATION           = 1
OLD_CACHE_DURATION           = 14
TRENDING_CACHE_DURATION      = 1
QUALITY_OLD_CACHE_DURATION   = int(os.environ.get("QUALITY_OLD_CACHE_DURATION", "90"))
QUALITY_BG_CONCURRENCY       = int(os.environ.get("QUALITY_BG_CONCURRENCY", "5"))
# NUOVO: Concorrenza allineata a 5 per evitare colli di bottiglia
MDBLIST_CONCURRENCY          = int(os.environ.get("MDBLIST_CONCURRENCY", "5"))

DIGITAL_RELEASE_MIN_AGE_DAYS = 1
DIGITAL_RELEASE_MAX_AGE_DAYS = 30

COMPOSITE_CACHE_TTL        = int(os.environ.get("COMPOSITE_CACHE_TTL", "604800"))
COMPOSITE_MAX_ENTRIES      = int(os.environ.get("COMPOSITE_MAX_ENTRIES", "0"))

def _parse_bool_env(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if not val: return default
    return val not in ("0", "false", "no")

# Rating Score Weight Defaults
MOVIE_WEIGHTS = {
    "letterboxd":     0.8, "trakt":          0, "tomatoes":       0.2, "popcorn":        0,
    "imdb":           0, "metacritic":     0, "metacriticuser": 0, "tmdb":           0,
    "rogerebert":     0, "myanimelist":    0,
}

TV_WEIGHTS = {
    "trakt":          0.8, "tomatoes":       0.2, "popcorn":        0, "imdb":           0,
    "metacritic":     0, "metacriticuser": 0, "tmdb":           0, "myanimelist":    0,
}

BADGE_FILES: dict[str, str] = {
    "4K":     "4K", "1080P":  "1080p", "REMUX":  "Remux", "WEBDL":  "Web",
    "DV":     "DV", "HDR10+": "HDR10+", "HDR10":  "HDR10",
}

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 53: "Thriller",
    10752: "War", 37: "Western", 10759: "Action", 10762: "Kids", 
    10763: "News", 10764: "Reality", 10765: "Sci-Fi", 10766: "Soap", 
    10767: "Talk", 10768: "War",
}

GENRE_PRIORITY = [
    27, 53, 9648, 878, 10765, 80, 35, 10749, 14, 16, 10751,
    28, 10759, 36, 10402, 10752, 10768, 37, 99, 18, 12,
    10764, 10762, 10763, 10766, 10767,
]

QUALITY_LABELS: dict[str, str] = {
    "4K":     "4K", "1080P":  "1080p", "REMUX":  "Remux", "WEBDL":  "Web",
    "DV":     "DV", "HDR10+": "HDR10+", "HDR10":  "HDR10", "ATMOS":  "Atmos", "DTSX":   "DTS:X",
}

SCORE_NORMALISERS = {
    "imdb":           lambda v: (v / 10)  * 100, "letterboxd":     lambda v: (v / 5)   * 100,
    "trakt":          lambda v: v, "tomatoes":       lambda v: v, "popcorn":        lambda v: v,
    "metacritic":     lambda v: v, "metacriticuser": lambda v: (v / 10)  * 100,
    "tmdb":           lambda v: v, "rogerebert":      lambda v: (v / 4)   * 100,
    "myanimelist":    lambda v: (v / 10)  * 100,
}

# NUOVO: Ampliata la priorità dei Sash con tag dinamici sulle release
SASH_PRIORITY: list[str] = [
    "next_episode",  # Es: "Prossimo Ep: 24 Ott" (Molto utile averlo in cima)
    "finale",        # Es: "Stagione Finale"
    "upcoming",      # Es: "Prossime Uscite"
    "wins",
    "gg_wins",
    "festival",
    "pic_noms",
    "gg_noms",
    "studio",
    "director",
    "cast",
    "trending",
    "cult",
    "foreign",
    "new_release",
    "returning",     # Es: "In Corso"
    "ended",         # Es: "Serie Terminata"
    "metacritic",
    "true_story",
    "structural",
]

# V2 Features Defaults
FROSTED_GLASS_INTENSITY   = 25
GRADIENT_TOP_INTENSITY    = 50
GRADIENT_BOTTOM_INTENSITY = 80
DOM_COLOR_TOP             = False
DOM_COLOR_BOT             = False
DOM_COLOR_SASH            = False
SASH_STYLE                = "ribbon"
TEXT_FONT_FAMILY          = "Inter"
TEXT_DROP_SHADOW          = False
USE_ORIGINAL_LOGO_COLOR   = False
MINIMAL_PILL_SCALE        = 1.0
