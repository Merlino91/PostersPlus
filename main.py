#main.py
import asyncio
import hashlib
import hmac
import io
import logging
import os
import re
import httpx
import numpy as np
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont, ImageFilter
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _uv_logger = logging.getLogger(_uv_name)
    _uv_logger.handlers = []
    _uv_logger.propagate = True


class _TruncateUrlFilter(logging.Filter):
    _MAX = 80
    _KEY_RE = re.compile(
        r'((?:tmdb_key|mdblist_key|access_key|api_key|apikey)=)[^&\s\'\"]*',
        re.IGNORECASE,
    )

    @classmethod
    def _redact(cls, value):
        if isinstance(value, str):
            return cls._KEY_RE.sub(r'\1***', value)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "uvicorn.access"
            and isinstance(record.args, tuple)
            and len(record.args) >= 3
        ):
            path = record.args[2]
            if isinstance(path, str):
                path = self._KEY_RE.sub(r'\1***', path)
                if len(path) > self._MAX:
                    path = path[: self._MAX] + "…"
                record.args = (record.args[0], record.args[1], path) + record.args[3:]

        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._redact(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._redact(v) for k, v in record.args.items()}

        if record.exc_info and not record.exc_text:
            import traceback
            record.exc_text = self._redact(
                "".join(traceback.format_exception(*record.exc_info))
            )
        elif record.exc_text:
            record.exc_text = self._redact(record.exc_text)

        return True


_url_filter = _TruncateUrlFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_url_filter)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_render_inflight: dict[str, "asyncio.Future[bytes]"] = {}
_quality_bg_inflight: set[str] = set()
_quality_bg_semaphore: "asyncio.Semaphore | None" = None

_rating_fetch_inflight:         dict[str, asyncio.Event] = {}
_rating_backoff:                dict[str, float]          = {} 
_rating_fail_count:             dict[str, int]            = {}
_mdblist_semaphore:             "asyncio.Semaphore | None" = None

_mdblist_key_cooldown: dict[str, float] = {}


async def _background_quality_fetch(
    imdb_id: str,
    media_type: str,
    season: int,
    episode: int,
    release_date: str | None,
) -> None:
    global _quality_bg_semaphore
    if _quality_bg_semaphore is None:
        _quality_bg_semaphore = asyncio.Semaphore(_cfg.QUALITY_BG_CONCURRENCY)
    try:
        async with _quality_bg_semaphore:
            if _HTTP_CLIENT is None:
                return
            await _with_retry(
                fetch_quality_from_aiostreams,
                _HTTP_CLIENT, imdb_id, media_type, season, episode, release_date,
            )
            logger.info(f"Background quality fetch complete for {imdb_id}")
    except Exception as exc:
        logger.warning(f"Background quality fetch failed for {imdb_id}: {exc}")
    finally:
        _quality_bg_inflight.discard(imdb_id)

from age_badge import draw_quality_age_badge, draw_tier_bar
from awards import FETCH_FAILED, _RateLimited, draw_award_badge, draw_award_sash, parse_mdblist_awards
from cache import (
    get_cached_quality,
    get_cached_rating,
    get_cached_final_poster,
    set_cached_final_poster,
    init_db,
    is_digital_release,
    set_cached_rating,
    delete_cached_tmdb_metadata,
    prune_caches,
)
from digital_release import digital_release_poll_loop
import config as _cfg
from discovery import (
    ALL_PRIORITY_SLOTS,
    FESTIVAL_KEYWORDS,
    DiscoveryMeta,
    extract_discovery_meta,
    pick_sash,
)
from quality import (
    BadgeItem,
    fetch_quality_from_aiostreams,
    get_resized_badge,
    parse_quality,
    render_badges_left,
)
from ratings import calculate_weighted_score, draw_score_bar, fetch_rating, draw_score_bar_vertical
from tmdb import composite_logo, fetch_logo, fetch_poster_metadata, fetch_poster_image, fetch_backdrop_image, fetch_trending_rank


_HTTP_CLIENT: httpx.AsyncClient | None = None

def _make_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0),
        limits=httpx.Limits(
            max_connections=40,
            max_keepalive_connections=20,
            keepalive_expiry=30,
        ),
        headers={"Accept-Encoding": "identity"},
        http2=False,
    )

_TMDB_ID_RE  = re.compile(r'^\d{1,10}$')
_IMDB_ID_RE  = re.compile(r'^tt\d{1,10}$')
_VALID_TYPES = frozenset({"movie", "tv", "series"})


def _check_tmdb_id(val: str) -> None:
    if not _TMDB_ID_RE.match(val):
        raise HTTPException(status_code=400, detail="Invalid tmdb_id")


def _check_imdb_id(val: str) -> None:
    if not _IMDB_ID_RE.match(val):
        raise HTTPException(status_code=400, detail="Invalid imdb_id")


def _check_type(val: str) -> None:
    if val not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail="Invalid type")


def _resolve_tmdb_key(query_key: str) -> str | None:
    if query_key:
        return query_key
    if _cfg.SERVER_TMDB_KEY:
        return _cfg.SERVER_TMDB_KEY
    return None


def _resolve_mdblist_key(query_key: str) -> str | None:
    if query_key:
        return query_key
    if _cfg.SERVER_MDBLIST_KEY:
        return _cfg.SERVER_MDBLIST_KEY
    return None


@dataclass
class RequestConfig:
    show_award_sash:     bool = field(default_factory=lambda: _cfg.SHOW_AWARD_SASH)
    badge_display_mode:  int  = field(default_factory=lambda: _cfg.BADGE_DISPLAY_MODE)
    rating_display_mode: int  = field(default_factory=lambda: _cfg.SHOW_RATING_DISPLAY_MODE)

    accent_bar_font_size_ratio:    float = field(default_factory=lambda: _cfg.ACCENT_BAR_MODE_FONT_SIZE_RATIO)
    numeric_score_font_size_ratio: float = field(default_factory=lambda: _cfg.NUMERIC_SCORE_MODE_FONT_SIZE_RATIO)
    accent_bar_y_offset:           float = field(default_factory=lambda: _cfg.ACCENT_BAR_MODE_FONT_Y_OFFSET)
    numeric_score_y_offset:        float = field(default_factory=lambda: _cfg.NUMERIC_SCORE_MODE_FONT_Y_OFFSET)
    score_glow_threshold:          int   = field(default_factory=lambda: _cfg.SCORE_GLOW_THRESHOLD)
    score_glow_blur:               int   = field(default_factory=lambda: _cfg.SCORE_GLOW_BLUR)
    score_glow_alpha:              int   = field(default_factory=lambda: _cfg.SCORE_GLOW_ALPHA)
    minimalist_mode_font_size_ratio:  float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_SIZE_RATIO)
    minimalist_mode_font_x_offset: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_X_OFFSET)
    minimalist_mode_font_y_offset: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_Y_OFFSET)

    logo_max_w_ratio:  float = field(default_factory=lambda: _cfg.LOGO_MAX_W_RATIO)
    logo_max_h_ratio:  float = field(default_factory=lambda: _cfg.LOGO_MAX_H_RATIO)
    logo_bottom_ratio: float = field(default_factory=lambda: _cfg.LOGO_BOTTOM_RATIO)

    badge_height:    int   = field(default_factory=lambda: _cfg.BADGE_HEIGHT)
    badge_gap:       int   = field(default_factory=lambda: _cfg.BADGE_GAP)
    badge_anchor_x:  float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_X_RATIO)
    badge_anchor_y:  float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_Y_RATIO)

    movie_weights: dict | None = None
    tv_weights:    dict | None = None

    logo_language: str = field(default_factory=lambda: _cfg.DEFAULT_LOGO_LANGUAGE)
    sash_priority: list[str] = field(default_factory=lambda: list(_cfg.SASH_PRIORITY))
    muted: bool = False
    textless: bool = False
    score_color_mode: int = 2
    sash_badge: bool = False 
    sash_badge_x: float = 0.62 
    sash_badge_y: float = 0.04 

    frosted_glass_intensity: int = field(default_factory=lambda: _cfg.FROSTED_GLASS_INTENSITY)
    gradient_top_intensity: int = field(default_factory=lambda: _cfg.GRADIENT_TOP_INTENSITY)
    gradient_bottom_intensity: int = field(default_factory=lambda: _cfg.GRADIENT_BOTTOM_INTENSITY)
    dominant_color_logic: bool = field(default_factory=lambda: _cfg.DOMINANT_COLOR_LOGIC)
    sash_style: str = field(default_factory=lambda: _cfg.SASH_STYLE)
    text_font_family: str = field(default_factory=lambda: _cfg.TEXT_FONT_FAMILY)
    text_drop_shadow: bool = field(default_factory=lambda: _cfg.TEXT_DROP_SHADOW)
    use_original_logo_color: bool = field(default_factory=lambda: _cfg.USE_ORIGINAL_LOGO_COLOR)
    minimal_pill_scale: float = field(default_factory=lambda: _cfg.MINIMAL_PILL_SCALE)


def _parse_bool(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no")


def _parse_weights(raw: str | None, sources: list[str]) -> dict | None:
    if not raw:
        return None
    out = {}
    try:
        for part in raw.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            key, val = part.split(":", 1)
            key = key.strip().lower()
            if key in sources:
                out[key] = max(0.0, min(1.0, float(val)))
    except Exception:
        return None
    return out if out else None


def _parse_sash_priority(raw: str | None) -> list[str]:
    if not raw:
        return list(_cfg.SASH_PRIORITY)
    tokens = [s.strip() for s in raw.split(",") if s.strip()]
    excluded  = {t[1:] for t in tokens if t.startswith("-") and t[1:] in ALL_PRIORITY_SLOTS}
    active    = [t      for t in tokens if not t.startswith("-") and t in ALL_PRIORITY_SLOTS]
    if not active and not excluded:
        return list(_cfg.SASH_PRIORITY)
    active_set = set(active)
    for slot in _cfg.SASH_PRIORITY:
        if slot not in active_set and slot not in excluded:
            active.append(slot)
    return active


def build_request_config(params: dict) -> RequestConfig:
    cfg = RequestConfig()

    def _b(key, default): return _parse_bool(params.get(key), default)

    def _f(key, default, lo: float, hi: float):
        try:
            return max(lo, min(hi, float(params[key]))) if key in params else default
        except (ValueError, TypeError):
            return default

    def _i(key, default, lo: int, hi: int):
        try:
            return max(lo, min(hi, int(params[key]))) if key in params else default
        except (ValueError, TypeError):
            return default

    cfg.show_award_sash         = _b("show_award_sash",        cfg.show_award_sash)
    cfg.muted                   = _b("muted",                  cfg.muted)
    cfg.textless                = _b("textless",               cfg.textless)
    cfg.sash_badge              = _b("sash_badge",             cfg.sash_badge)

    def _s(key, default):
        return params.get(key, default).strip() if key in params else default

    cfg.frosted_glass_intensity = _i("frosted_glass_intensity", cfg.frosted_glass_intensity, 0, 250)
    cfg.gradient_top_intensity = _i("gradient_top_intensity", cfg.gradient_top_intensity, 0, 100)
    cfg.gradient_bottom_intensity = _i("gradient_bottom_intensity", cfg.gradient_bottom_intensity, 0, 100)
    cfg.dominant_color_logic = _b("dominant_color_logic", cfg.dominant_color_logic)
    cfg.sash_style = _s("sash_style", cfg.sash_style)
    
    font_family = _s("text_font_family", cfg.text_font_family)
    if font_family not in ("Inter", "Ubuntu", "Roboto", "Montserrat", "BebasNeue", "Poppins"):
        font_family = "Inter"
    cfg.text_font_family = font_family

    cfg.text_drop_shadow = _b("text_drop_shadow", cfg.text_drop_shadow)
    cfg.use_original_logo_color = _b("use_original_logo_color", cfg.use_original_logo_color)
    cfg.minimal_pill_scale = _f("minimal_pill_scale", cfg.minimal_pill_scale, 0.1, 5.0)

    cfg.sash_badge_x            = _f("sash_badge_x",           cfg.sash_badge_x,           0.0, 1.0)
    cfg.sash_badge_y            = _f("sash_badge_y",           cfg.sash_badge_y,           0.0, 1.0)
    cfg.score_color_mode        = _i("score_color_mode",       cfg.score_color_mode,       0,   2)
    cfg.badge_display_mode      = _i("badge_display_mode",     cfg.badge_display_mode,     0,   4)
    cfg.rating_display_mode     = _i("rating_display_mode",    cfg.rating_display_mode,    0,   4)

    if "show_quality_badges" in params and "badge_display_mode" not in params:
        if _parse_bool(params.get("show_quality_badges"), True):
            cfg.badge_display_mode = 1
        else:
            cfg.badge_display_mode = 0

    cfg.accent_bar_font_size_ratio    = _f("accent_bar_font_size_ratio",    cfg.accent_bar_font_size_ratio,    0.0, 0.5)
    cfg.numeric_score_font_size_ratio = _f("numeric_score_font_size_ratio", cfg.numeric_score_font_size_ratio, 0.0, 0.5)
    cfg.accent_bar_y_offset           = _f("accent_bar_y_offset",           cfg.accent_bar_y_offset,           0.0, 1.0)
    cfg.numeric_score_y_offset        = _f("numeric_score_y_offset",        cfg.numeric_score_y_offset,        0.0, 1.0)
    cfg.score_glow_threshold          = _i("score_glow_threshold",          cfg.score_glow_threshold,          0,   100)
    cfg.score_glow_blur               = _i("score_glow_blur",               cfg.score_glow_blur,               0,   50)
    cfg.score_glow_alpha              = _i("score_glow_alpha",              cfg.score_glow_alpha,              0,   255)
    cfg.minimalist_mode_font_size_ratio = _f("minimalist_mode_font_size_ratio", cfg.minimalist_mode_font_size_ratio, 0.0, 0.5)
    cfg.minimalist_mode_font_x_offset = _f("minimalist_mode_font_x_offset", cfg.minimalist_mode_font_x_offset, 0.0, 1.0)
    cfg.minimalist_mode_font_y_offset = _f("minimalist_mode_font_y_offset", cfg.minimalist_mode_font_y_offset, 0.0, 1.0)

    cfg.logo_max_w_ratio  = _f("logo_max_w_ratio",  cfg.logo_max_w_ratio,  0.0, 1.5)
    cfg.logo_max_h_ratio  = _f("logo_max_h_ratio",  cfg.logo_max_h_ratio,  0.0, 1.0)
    cfg.logo_bottom_ratio = _f("logo_bottom_ratio", cfg.logo_bottom_ratio, 0.0, 1.0)

    cfg.badge_height   = _i("badge_height",   cfg.badge_height,   1,   200)
    cfg.badge_gap      = _i("badge_gap",      cfg.badge_gap,      0,   100)
    cfg.badge_anchor_x = _f("badge_anchor_x", cfg.badge_anchor_x, 0.0, 1.0)
    cfg.badge_anchor_y = _f("badge_anchor_y", cfg.badge_anchor_y, 0.0, 1.0)

    all_sources = list(_cfg.MOVIE_WEIGHTS.keys())
    cfg.movie_weights = _parse_weights(params.get("movie_weights"), all_sources)

    tv_sources = list(_cfg.TV_WEIGHTS.keys())
    cfg.tv_weights = _parse_weights(params.get("tv_weights"), tv_sources)

    cfg.logo_language = (params.get("logo_language", cfg.logo_language).strip().lower())
    cfg.sash_priority = _parse_sash_priority(params.get("sash_priority"))

    return cfg


async def _resolved(value):
    return value


async def _with_retry(coro_fn, *args, **kwargs):
    result = await coro_fn(*args, **kwargs)
    if result is FETCH_FAILED:
        result = await coro_fn(*args, **kwargs)
    return result


def _text_center(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    cx: float,
    cy: float,
) -> tuple[float, float]:
    bbox = draw.textbbox((0, 0), text, font=font)
    bbox_width = bbox[2] - bbox[0]
    x = cx - bbox_width / 2 - bbox[0]
    if hasattr(font, 'getmetrics'):
        ascent, descent = font.getmetrics()
        optical_adjust = int(ascent * 0.22)
        y = cy - (ascent + descent) / 2 - descent + optical_adjust
    else:
        bbox_height = bbox[3] - bbox[1]
        y = cy - bbox_height / 2 - bbox[1]
    return x, y


def _get_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    small_img = image.copy()
    small_img.thumbnail((50, 50))
    small_img = small_img.convert("RGB")
    colors = small_img.getcolors(2500)
    if not colors:
        return (100, 100, 100)

    colors.sort(key=lambda t: t[0], reverse=True)
    for count, color in colors:
        luminanza = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
        if 40 < luminanza < 215:
            return color

    return colors[0][1]


def draw_custom_top_tag(image: Image.Image, text: str, scale: float = 1.0, bg_color: tuple = (20, 20, 20), font_family: str = "Inter") -> Image.Image:
    width, height = image.size
    base_font_size = int(24 * scale)
    try:
        font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{font_family}-Bold.ttf"), base_font_size)
    except IOError:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(image)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    pad_x = int(20 * scale)
    pad_y = int(12 * scale)
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    
    pill_x = (width - pill_w) // 2
    pill_y = 0 
    
    r = int(10 * scale) 
    
    overlay = Image.new("RGBA", (width, height), (0,0,0,0))
    overlay_draw = ImageDraw.Draw(overlay)
    
    overlay_draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=r,
        fill=(*bg_color, 240)
    )
    overlay_draw.rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + r],
        fill=(*bg_color, 240)
    )
    
    lum = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    text_color = (255, 255, 255) if lum < 150 else (0, 0, 0)
    
    text_x = pill_x + pad_x
    if hasattr(font, 'getmetrics'):
        ascent, descent = font.getmetrics()
        text_y = pill_y + (pill_h - (ascent + descent)) // 2
    else:
        text_y = pill_y + pad_y
        
    overlay_draw.text((text_x, text_y), text, font=font, fill=text_color)
    
    return Image.alpha_composite(image.convert("RGBA"), overlay)


_GENRE_TINT: dict[str, tuple[float, float, float]] = {
    "Horror":      (3.2, 0.3, 0.3),   
    "Thriller":    (0.4, 2.2, 0.5),   
    "Mystery":     (1.0, 0.3, 3.0),   
    "Sci-Fi":      (0.3, 1.2, 3.2),   
    "Fantasy":     (1.6, 0.3, 3.0),   
    "Action":      (3.0, 0.8, 0.3),   
    "Adventure":   (2.6, 1.5, 0.3),   
    "Animation":   (0.4, 0.8, 3.2),   
    "Comedy":      (2.6, 2.4, 0.3),   
    "Crime":       (2.4, 0.2, 0.2),   
    "Documentary": (0.3, 2.2, 2.4),   
    "Drama":       (0.3, 0.3, 2.6),   
    "Family":      (2.6, 1.2, 0.3),   
    "History":     (2.2, 1.1, 0.3),   
    "Music":       (2.8, 0.3, 2.2),   
    "Romance":     (3.0, 0.3, 0.9),   
    "War":         (0.9, 1.6, 0.3),   
    "Western":     (2.8, 1.1, 0.2),   
    "Kids":        (0.3, 1.1, 3.0),   
    "Reality":     (2.4, 0.8, 0.3),   
    "Soap":        (2.6, 0.3, 0.9),   
    "Talk":        (0.3, 1.6, 2.4),   
    "News":        (0.3, 0.5, 2.6),   
}
_FALLBACK_DEFAULT_TINT = (1.0, 1.0, 1.4)


def _make_fallback_canvas(genre_ids: list[int] | None = None) -> Image.Image:
    tint = _FALLBACK_DEFAULT_TINT
    if genre_ids:
        gid_set = set(genre_ids)
        for gid in _cfg.GENRE_PRIORITY:
            if gid in gid_set:
                name = _cfg.GENRE_MAP.get(gid)
                if name and name in _GENRE_TINT:
                    tint = _GENRE_TINT[name]
                    break

    r_mult, g_mult, b_mult = tint
    W, H = _cfg.POSTER_WIDTH, _cfg.POSTER_HEIGHT
    t    = np.linspace(0, np.pi, H, dtype=np.float32)
    v    = (10 + 8 * np.sin(t)).astype(np.float32)
    arr  = np.zeros((H, W, 4), dtype=np.uint8)
    arr[:, :, 0] = np.minimum(255, v * r_mult).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 1] = np.minimum(255, v * g_mult).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 2] = np.minimum(255, v * b_mult).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def build_poster(
    image: Image.Image,
    score: int | str,
    genre: str,
    cfg: RequestConfig,
    logo: Image.Image | None = None,
    fallback_title: str | None = None,
    discovery_meta: DiscoveryMeta | None = None,
    quality_tokens: list[str] | None = None,
    release_year: str | None = None,
    age_rating: int | None = None,
    no_poster: bool = False,
) -> Image.Image:

    width, height = image.size
    draw = ImageDraw.Draw(image)

    dom_color = _get_dominant_color(image) if getattr(cfg, 'dominant_color_logic', False) else (0, 0, 0)

    # --- TOP GRADIENT ---
    if cfg.gradient_top_intensity > 0:
        top_height = int(height * 0.25)
        top_max_alpha = int((cfg.gradient_top_intensity / 100) * 255)
        t_top = np.linspace(0, 1, top_height, dtype=np.float32)
        eased_top = ((1 - t_top) * top_max_alpha).astype(np.uint8)
        top_array = np.broadcast_to(eased_top[:, np.newaxis], (top_height, width)).copy()
        top_overlay = Image.fromarray(top_array, mode="L")

        top_tinted = Image.new("RGBA", (width, top_height), (dom_color[0], dom_color[1], dom_color[2], 0))
        top_tinted.putalpha(top_overlay)
        image.paste(top_tinted, (0, 0), mask=top_tinted)

    # --- BOTTOM GRADIENT ---
    bottom_height = int(height * 0.35)
    bottom_start = height - bottom_height

    if getattr(cfg, 'frosted_glass_intensity', 0) > 0:
        bottom_crop = image.crop((0, bottom_start, width, height))
        blurred_bottom = bottom_crop.filter(ImageFilter.GaussianBlur(radius=cfg.frosted_glass_intensity))

        t_blur = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_blur = ((t_blur ** 1.5) * 255).astype(np.uint8)
        blur_array = np.broadcast_to(eased_blur[:, np.newaxis], (bottom_height, width)).copy()
        blur_mask = Image.fromarray(blur_array, mode="L")

        image.paste(blurred_bottom, (0, bottom_start), mask=blur_mask)

    if cfg.gradient_bottom_intensity > 0:
        bottom_max_alpha = int((cfg.gradient_bottom_intensity / 100) * 255)
        bottom_curve = 1.2

        t_bot = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_bot = ((1 - (1 - t_bot) ** bottom_curve) * bottom_max_alpha).astype(np.uint8)
        bottom_array = np.broadcast_to(eased_bot[:, np.newaxis], (bottom_height, width)).copy()
        bottom_overlay = Image.fromarray(bottom_array, mode="L")

        bottom_tinted = Image.new("RGBA", (width, bottom_height), (dom_color[0], dom_color[1], dom_color[2], 0))
        bottom_tinted.putalpha(bottom_overlay)
        image.paste(bottom_tinted, (0, bottom_start), mask=bottom_tinted)


    mode   = cfg.badge_display_mode
    tokens = quality_tokens or []

    if cfg.rating_display_mode == 4:
        mode = 0  

    if mode == 1:
        draw_quality_age_badge(
            image,
            age_rating,
            tokens,
            anchor_x_ratio=cfg.badge_anchor_x,
            anchor_y_ratio=cfg.badge_anchor_y,
            badge_height=cfg.badge_height,
        )

    elif mode == 3:
        draw_quality_age_badge(
            image,
            age_rating,
            [],
            anchor_x_ratio=cfg.badge_anchor_x,
            anchor_y_ratio=cfg.badge_anchor_y,
            badge_height=cfg.badge_height,
            always_silver=True,
        )

    elif mode == 4:
        draw_tier_bar(
            image,
            tokens,
            anchor_x_ratio=cfg.badge_anchor_x,
            anchor_y_ratio=cfg.badge_anchor_y,
            bar_height=cfg.badge_height,
        )

    elif mode == 2:
        allowed_tokens  = {"4K", "1080P", "REMUX", "WEBDL", "DV", "HDR10+", "HDR10"}
        filtered_tokens = [t for t in tokens if t in allowed_tokens]

        if filtered_tokens:
            bx = int(width  * cfg.badge_anchor_x)
            by = int(height * cfg.badge_anchor_y)

            badge_items: list[BadgeItem] = [
                (get_resized_badge(token, cfg.badge_height), _cfg.QUALITY_LABELS.get(token, token))
                for token in filtered_tokens
            ]

            render_badges_left(
                image, badge_items,
                x_start=bx, y_top=by,
                badge_height=cfg.badge_height,
                badge_gap=cfg.badge_gap,
            )

    if logo:
        composite_logo(
            image, logo,
            max_w_ratio=cfg.logo_max_w_ratio,
            max_h_ratio=cfg.logo_max_h_ratio,
            bottom_ratio=cfg.logo_bottom_ratio,
        )
    elif fallback_title:
        try:
            font_size = int(width * 0.1)
            font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
        except IOError:
            font = ImageFont.load_default()

        title_cy = height - int(height * 0.3)
        max_width = int(width * 0.82)

        while True:
            bbox = draw.textbbox((0, 0), fallback_title, font=font)
            text_width = bbox[2] - bbox[0]
            if text_width <= max_width or font_size <= 24: 
                break
            font_size -= 2 
            try:
                font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
            except IOError:
                break

        tx, ty = _text_center(draw, fallback_title, font, width / 2, title_cy) 
        shadow_offset = max(2, int(font_size * 0.04)) 
        draw.text((tx + shadow_offset, ty + shadow_offset), fallback_title, font=font, fill=(0, 0, 0, 180))
        draw.text((tx, ty), fallback_title, font=font, fill=(255, 255, 255, 255))

        if no_poster:
            try:
                wm_font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), 18)
            except IOError:
                wm_font = ImageFont.load_default()
            wm_text = "Posters+ fallback"
            wm_bb   = draw.textbbox((0, 0), wm_text, font=wm_font)
            wm_x    = (width - (wm_bb[2] - wm_bb[0])) // 2
            wm_y    = ty + (wm_bb[3] - wm_bb[1]) + int(font_size * 1.4) 
            draw.text((wm_x, wm_y), wm_text, font=wm_font, fill=(160, 160, 160, 110))

    if cfg.rating_display_mode != 0:

        if cfg.rating_display_mode == 1:
            font_size = int(width * cfg.accent_bar_font_size_ratio)
            label = f"{genre} · {release_year}" if release_year else genre
            rating_cy = height * cfg.accent_bar_y_offset

            try:
                font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
            except IOError:
                font_meta = ImageFont.load_default()

            tx, ty = _text_center(draw, label, font_meta, width / 2, rating_cy)
            if getattr(cfg, 'text_drop_shadow', False):
                draw.text(
                    (tx + 2, ty - int(font_size * 0.10) + 2),
                    label,
                    font=font_meta,
                    fill=(0, 0, 0, 150),
                )
            draw.text(
                (tx, ty - int(font_size * 0.10)),
                label,
                font=font_meta,
                fill=(200, 200, 200, 255),
            )
            draw_score_bar(
                image, score,
                glow_threshold=cfg.score_glow_threshold,
                glow_blur=cfg.score_glow_blur,
                glow_alpha=cfg.score_glow_alpha,
                color_mode=cfg.score_color_mode,
            )

        elif cfg.rating_display_mode == 2:
            font_size = int(width * cfg.numeric_score_font_size_ratio)
            label = f"{genre} ★ {score}"
            rating_cy = height * cfg.numeric_score_y_offset

            try:
                font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
            except IOError:
                font_meta = ImageFont.load_default()

            tx, ty = _text_center(draw, label, font_meta, width / 2, rating_cy)
            if getattr(cfg, 'text_drop_shadow', False):
                draw.text(
                    (tx + 2, ty - int(font_size * 0.10) + 2),
                    label,
                    font=font_meta,
                    fill=(0, 0, 0, 150),
                )
            draw.text(
                (tx, ty - int(font_size * 0.10)),
                label,
                font=font_meta,
                fill=(200, 200, 200, 255),
            )

        elif cfg.rating_display_mode == 3:
            font_size = int(width * cfg.minimalist_mode_font_size_ratio)

            try:
                font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
            except IOError:
                font_meta = ImageFont.load_default()

            y = round(height * cfg.minimalist_mode_font_y_offset)
            right_edge = width - int(width * cfg.minimalist_mode_font_x_offset)

            year_text  = str(release_year or "")
            genre_text = genre

            pip_gap = int(font_size * 0.55)
            pip_w   = max(4, int(font_size * 0.18))
            pip_h   = int(font_size * 1.4)

            genre_bb = draw.textbbox((0, 0), genre_text, font=font_meta)
            genre_w  = genre_bb[2] - genre_bb[0]

            if year_text:
                year_bb = draw.textbbox((0, 0), year_text, font=font_meta)
                year_w  = year_bb[2] - year_bb[0]
            else:
                year_w = 0

            pip_x  = right_edge - year_w - pip_gap - pip_w
            pip_cy = round(y + font_size * 0.60)

            genre_x = pip_x - pip_gap - genre_w
            if getattr(cfg, 'text_drop_shadow', False):
                draw.text((genre_x + 2, y + 2), genre_text, font=font_meta, fill=(0, 0, 0, 150))
            draw.text((genre_x, y), genre_text, font=font_meta, fill=(235, 235, 235, 255))

            if year_text:
                year_x = pip_x + pip_w + pip_gap
                if getattr(cfg, 'text_drop_shadow', False):
                    draw.text((year_x + 2, y + 2), year_text, font=font_meta, fill=(0, 0, 0, 150))
                draw.text((year_x, y), year_text, font=font_meta, fill=(235, 235, 235, 255))

            if score not in ("N/A", None):
                draw_score_bar_vertical(
                    image,
                    score,
                    x=pip_x,
                    y_center=pip_cy,
                    height=pip_h,
                    width=pip_w,
                    color_mode=cfg.score_color_mode,
                )

    if cfg.show_award_sash and discovery_meta is not None:
        sash_result = pick_sash(discovery_meta, cfg.sash_priority)
        if sash_result is not None:
            label, sash_type = sash_result
            if cfg.sash_style == "minimal_pill":
                dom_color_pill = dom_color if cfg.dominant_color_logic else (20, 20, 20)
                image = draw_custom_top_tag(image, label, scale=cfg.minimal_pill_scale, bg_color=dom_color_pill, font_family=cfg.text_font_family)
            elif cfg.sash_style == "corner_badge" or cfg.sash_badge:
                image = draw_award_badge(image, label, sash_type=sash_type,
                                         x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y)
            else:
                image = draw_award_sash(image, label, sash_type=sash_type, muted=cfg.muted)

    return image


async def _cache_prune_loop() -> None:
    await asyncio.sleep(300)
    while True:
        logger.info("Running scheduled cache prune")
        await asyncio.get_running_loop().run_in_executor(None, prune_caches)

        _now = asyncio.get_running_loop().time()
        
        expired = [k for k, v in _rating_backoff.items() if v <= _now]
        for k in expired:
            del _rating_backoff[k]
            
        expired_cooldowns = [k for k, v in _mdblist_key_cooldown.items() if v <= _now]
        for k in expired_cooldowns:
            del _mdblist_key_cooldown[k]
            
        if expired:
            logger.debug(f"Pruned {len(expired)} expired rating backoff entries")

        await asyncio.sleep(6 * 3600)   


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _HTTP_CLIENT, _configurator_html
    init_db()
    logger.info(f"Cache initialised (composite TTL {_cfg.COMPOSITE_CACHE_TTL}s / "
                f"{_cfg.COMPOSITE_CACHE_TTL / 86400:.1f}d)")
    _HTTP_CLIENT = _make_http_client()
    logger.info("HTTP client initialised")
    _configurator_html = _load_configurator_html()
    prune_task   = asyncio.create_task(_cache_prune_loop())
    digital_task = asyncio.create_task(digital_release_poll_loop(_HTTP_CLIENT))
    yield
    prune_task.cancel()
    digital_task.cancel()
    with suppress(asyncio.CancelledError):
        await prune_task
    with suppress(asyncio.CancelledError):
        await digital_task
    await _HTTP_CLIENT.aclose()
    logger.info("HTTP client closed")


app = FastAPI(lifespan=lifespan)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(BASE_DIR, "fonts")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.middleware("http")
async def remove_server_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["server"] = "unknown"
    return response


@app.get("/server-caps")
async def server_caps(access_key: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY):
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {
        "tmdb_key_set":          bool(_cfg.SERVER_TMDB_KEY),
        "mdblist_key_set":       bool(_cfg.SERVER_MDBLIST_KEY),
        "aiostreams_configured": bool(_cfg.AIOSTREAMS_URL and _cfg.AIOSTREAMS_AUTH),
    }


_configurator_html: str | None = None


def _load_configurator_html() -> str:
    html_path = os.path.join(os.path.dirname(__file__), "configurator.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Configurator not found</h1><p>Place configurator.html alongside main.py</p>"


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def get_configurator(access_key: str = "", reload: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY):
        raise HTTPException(status_code=403, detail="Unauthorized. Provide ?access_key=<key>")
    global _configurator_html
    if reload:
        _configurator_html = _load_configurator_html()
        logger.info("Configurator HTML reloaded from disk")
    return HTMLResponse(content=_configurator_html or _load_configurator_html())


@app.get("/search")
async def search_proxy(
    q: str,
    tmdb_key: str = "",
    access_key: str = "",
):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY):
        raise HTTPException(status_code=403, detail="Unauthorized")
    if len(q) > 200:
        raise HTTPException(status_code=400, detail="Query too long")

    effective_key = _resolve_tmdb_key(tmdb_key)
    if not effective_key:
        raise HTTPException(status_code=400, detail="No TMDB API key available")

    if _HTTP_CLIENT is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    resp = await _HTTP_CLIENT.get(
        "https://api.themoviedb.org/3/search/multi",
        params={
            "api_key": effective_key,
            "query": q,
            "include_adult": "false",
            "page": "1",
        },
    )
    return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)


@app.get("/resolve-imdb")
async def resolve_imdb(
    tmdb_id: str,
    type: str = "movie",
    tmdb_key: str = "",
    access_key: str = "",
):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY):
        raise HTTPException(status_code=403, detail="Unauthorized")

    _check_tmdb_id(tmdb_id)
    _check_type(type)

    effective_key = _resolve_tmdb_key(tmdb_key)
    if not effective_key:
        raise HTTPException(status_code=400, detail="No TMDB API key available")

    endpoint = (
        f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids"
        if type == "tv"
        else f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids"
    )

    if _HTTP_CLIENT is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    resp = await _HTTP_CLIENT.get(endpoint, params={"api_key": effective_key})
    return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)


@app.get("/poster")
async def get_poster(
    request: Request,
    tmdb_id: str,
    imdb_id: str,
    type: str = "movie",
    quality: str = "",
    season: int = 1,
    episode: int = 1,
    access_key: str = "",
    mdblist_key: str = "",
    tmdb_key: str = "",
    show_award_sash: str | None = None,
    badge_display_mode: str | None = None,
    show_quality_badges: str | None = None,
    rating_display_mode: str | None = None,
    accent_bar_font_size_ratio: str | None = None,
    numeric_score_font_size_ratio: str | None = None,
    accent_bar_y_offset: str | None = None,
    numeric_score_y_offset: str | None = None,
    minimalist_mode_font_size_ratio: str | None = None,
    minimalist_mode_font_x_offset: str | None = None,
    minimalist_mode_font_y_offset: str | None = None,
    score_glow_threshold: str | None = None,
    score_glow_blur: str | None = None,
    score_glow_alpha: str | None = None,
    logo_max_w_ratio: str | None = None,
    logo_max_h_ratio: str | None = None,
    logo_bottom_ratio: str | None = None,
    badge_height: str | None = None,
    badge_gap: str | None = None,
    badge_anchor_x: str | None = None,
    badge_anchor_y: str | None = None,
    movie_weights: str | None = None,
    tv_weights: str | None = None,
    logo_language: str | None = None,
    sash_priority: str | None = None,
    muted: str | None = None,
    textless: str | None = None,
    score_color_mode: str | None = None,
    debug: str | None = None,
):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY):
        raise HTTPException(status_code=403, detail="Unauthorized, your access key is not valid for this instance.")

    _check_tmdb_id(tmdb_id)
    _check_imdb_id(imdb_id)
    _check_type(type)

    effective_tmdb_key    = _resolve_tmdb_key(tmdb_key)
    effective_mdblist_key = _resolve_mdblist_key(mdblist_key)

    if not effective_tmdb_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "No TMDB API key available. Either provide tmdb_key= as a query parameter "
                "or configure the TMDB_API_KEY environment variable on the server."
            ),
        )

    raw_params = {
        k: v for k, v in request.query_params.items()
        if k not in (
            "tmdb_id", "imdb_id", "mdblist_key", "tmdb_key", "type",
            "quality", "season", "episode", "access_key", "debug",
        )
    }
    rcfg = build_request_config(raw_params)

    if not quality:
        _params_hash = hashlib.md5(
            "&".join(f"{k}={v}" for k, v in sorted(raw_params.items())).encode()
        ).hexdigest()[:8]
        final_cache_key = f"{imdb_id}:{type}:{_params_hash}"
        cached_jpeg = get_cached_final_poster(final_cache_key)
        if cached_jpeg is not None:
            logger.info(f"Final poster cache hit for {final_cache_key}")
            etag = f'"{final_cache_key}"'
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304)
            _hit_resp = Response(content=cached_jpeg, media_type="image/jpeg")
            _hit_resp.headers["ETag"] = etag
            if _cfg.CDN_CACHE_TTL > 0:
                _hit_resp.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
            return _hit_resp
    else:
        final_cache_key = None

    _render_fut: "asyncio.Future[bytes] | None" = None
    if final_cache_key is not None:
        _existing_fut = _render_inflight.get(final_cache_key)
        if _existing_fut is not None:
            logger.info(f"Coalescing request for {final_cache_key}")
            try:
                _coal_resp = Response(content=await _existing_fut, media_type="image/jpeg")
                _coal_resp.headers["ETag"] = f'"{final_cache_key}"'
                if _cfg.CDN_CACHE_TTL > 0:
                    _coal_resp.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
                return _coal_resp
            except Exception:
                pass
        _render_fut = asyncio.get_running_loop().create_future()
        _render_fut.add_done_callback(
            lambda f: f.exception() if not f.cancelled() and f.exception() else None
        )
        _render_inflight[final_cache_key] = _render_fut

    cached_rating = get_cached_rating(imdb_id)

    if cached_rating is not None:
        (
            cached_ratings_dict,
            cached_genre,
            cached_release_date,
            cached_award_wins,
            cached_award_noms,
            cached_awards_fetched,
            cached_festival_label,
            cached_age_rating,
            cached_is_cult,
            cached_is_true_story,
            cached_is_metacritic,
        ) = cached_rating
    else:
        cached_ratings_dict   = None
        cached_genre          = None
        cached_release_date   = None
        cached_award_wins     = []
        cached_award_noms     = []
        cached_awards_fetched = False
        cached_festival_label = None
        cached_age_rating     = None
        cached_is_cult        = False
        cached_is_true_story  = False
        cached_is_metacritic  = False

    release_date_for_quality_ttl = cached_release_date
    rating_already_cached        = cached_rating is not None

    _rating_event_to_set: asyncio.Event | None = None
    _rating_backoff_active = False 

    if not rating_already_cached and effective_mdblist_key:
        _loop_now = asyncio.get_running_loop().time()

        _global_cooldown = _mdblist_key_cooldown.get(effective_mdblist_key, 0.0)
        if _loop_now < _global_cooldown:
            _remaining = _global_cooldown - _loop_now
            logger.debug(
                f"Rating fetch for {imdb_id} skipped "
                f"(MDBlist key rate-limit cooldown: {_remaining:.0f}s remaining)"
            )
            effective_mdblist_key = None
            _rating_backoff_active = True

        if effective_mdblist_key:
            _backoff_until = _rating_backoff.get(imdb_id)
            if _backoff_until is not None:
                if _loop_now < _backoff_until:
                    logger.debug(f"Rating fetch for {imdb_id} skipped (MDBlist per-title back-off active)")
                    effective_mdblist_key = None
                    _rating_backoff_active = True
                else:
                    del _rating_backoff[imdb_id]       
                    _rating_fail_count.pop(imdb_id, None)  

    if not rating_already_cached and effective_mdblist_key:
        _inflight_event = _rating_fetch_inflight.get(imdb_id)
        if _inflight_event is not None:
            logger.info(f"Rating fetch coalesced for {imdb_id} — awaiting in-flight fetch")
            await _inflight_event.wait()
            _refreshed = get_cached_rating(imdb_id)
            if _refreshed is not None:
                (
                    cached_ratings_dict,
                    cached_genre,
                    cached_release_date,
                    cached_award_wins,
                    cached_award_noms,
                    cached_awards_fetched,
                    cached_festival_label,
                    cached_age_rating,
                    cached_is_cult,
                    cached_is_true_story,
                    cached_is_metacritic,
                ) = _refreshed
                rating_already_cached        = True
                release_date_for_quality_ttl = cached_release_date
                logger.info(f"Rating coalesce succeeded for {imdb_id} — using cached result")
            else:
                _loop_now2    = asyncio.get_running_loop().time()
                _backoff_now2 = _rating_backoff.get(imdb_id)
                if _backoff_now2 is not None and _loop_now2 < _backoff_now2:
                    logger.debug(
                        f"Rating fetch for {imdb_id} suppressed after coalescence (back-off active)"
                    )
                    effective_mdblist_key = None
        else:
            _rating_event_to_set              = asyncio.Event()
            _rating_fetch_inflight[imdb_id]   = _rating_event_to_set

    if quality:
        quality_tokens = parse_quality(quality)
        cached_tokens  = None
    else:
        cached_tokens  = get_cached_quality(imdb_id, release_date_for_quality_ttl)
        quality_tokens = cached_tokens or []

    quality_needs_fetch = (
        rcfg.badge_display_mode in (1, 2, 4)
        and not quality
        and cached_tokens is None
    )

    quality_pending = False
    if quality_needs_fetch:
        if imdb_id not in _quality_bg_inflight:
            _quality_bg_inflight.add(imdb_id)
            asyncio.create_task(
                _background_quality_fetch(
                    imdb_id, type, season, episode,
                    release_date_for_quality_ttl,
                )
            )
            logger.info(f"Quality fetch deferred to background for {imdb_id}")
        else:
            logger.info(f"Quality background fetch already in progress for {imdb_id}")
        quality_needs_fetch = False
        quality_pending = True

    if not rating_already_cached and not effective_mdblist_key:
        logger.warning(
            f"No MDblist key for {imdb_id} and no cached rating — "
            "poster will be served without rating/award data."
        )

    effective_movie_weights = rcfg.movie_weights or _cfg.MOVIE_WEIGHTS
    effective_tv_weights    = rcfg.tv_weights    or _cfg.TV_WEIGHTS

    if _HTTP_CLIENT is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    client = _HTTP_CLIENT

    try:
        genre_ids, is_textless, logos, release_year, title, poster_path, backdrop_path, tmdb_data = (
            await fetch_poster_metadata(client, tmdb_id, effective_tmdb_key, type, rcfg.logo_language)
        )

        _gid_set = set(genre_ids)
        _tmdb_genre = "Unknown"
        for _gid in _cfg.GENRE_PRIORITY:
            if _gid in _gid_set:
                _candidate = _cfg.GENRE_MAP.get(_gid, "")
                if _candidate:
                    _tmdb_genre = _candidate
                    break

        _use_backdrop = bool(backdrop_path) and (poster_path is None or not is_textless)
        if _use_backdrop:
            logger.info(f"No textless poster for {tmdb_id} — using backdrop crop as portrait fallback")
            is_textless = True         

        if rating_already_cached or not effective_mdblist_key:
            rating_coro = _resolved(
                (cached_ratings_dict, cached_genre, cached_release_date, [], cached_age_rating)
            )
        else:
            global _mdblist_semaphore
            if _mdblist_semaphore is None:
                _mdblist_semaphore = asyncio.Semaphore(_cfg.MDBLIST_CONCURRENCY)

            async def _fetch_rating_gated(
                _client=client, _imdb_id=imdb_id, _key=effective_mdblist_key,
                _gids=genre_ids, _type=type,
                _mw=effective_movie_weights, _tw=effective_tv_weights,
            ):
                async with _mdblist_semaphore:
                    return await _with_retry(
                        fetch_rating,
                        _client, _imdb_id, _key, _gids, _type,
                        movie_weights=_mw, tv_weights=_tw,
                    )

            rating_coro = _fetch_rating_gated()

        is_no_poster = poster_path is None and not _use_backdrop
        if _use_backdrop:
            _image_coro = fetch_backdrop_image(client, tmdb_id, backdrop_path)
        elif is_no_poster:
            _image_coro = _resolved(_make_fallback_canvas(genre_ids))
        else:
            _image_coro = fetch_poster_image(client, tmdb_id, type, poster_path)

        (
            image,
            logo,
            rating_result,
            trending_rank,
        ) = await asyncio.gather(
            _image_coro,
            fetch_logo(client, logos, rcfg.logo_language, getattr(rcfg, 'use_original_logo_color', False)) if (is_textless and not is_no_poster) else _resolved(None),
            rating_coro,
            fetch_trending_rank(client, tmdb_id, effective_tmdb_key, type),
        )

        rate_limited  = isinstance(rating_result, _RateLimited)
        rating_failed = (
            not rating_already_cached
            and effective_mdblist_key
            and (rating_result is FETCH_FAILED or rate_limited)
        )

        if rating_failed:
            if rate_limited:
                if rating_result.retry_after:
                    backoff_secs = min(float(rating_result.retry_after), 3600.0)
                    logger.warning(
                        f"MDblist rate-limited {imdb_id} — honouring Retry-After "
                        f"({backoff_secs:.0f}s)"
                    )
                else:
                    backoff_secs = 3600.0
                    logger.warning(f"MDblist rate-limited {imdb_id} — using 1h default back-off")

                _global_window = min(backoff_secs, 120.0)
                _new_global_until = asyncio.get_running_loop().time() + _global_window
                
                if effective_mdblist_key:
                    current_cooldown = _mdblist_key_cooldown.get(effective_mdblist_key, 0.0)
                    if _new_global_until > current_cooldown:
                        _mdblist_key_cooldown[effective_mdblist_key] = _new_global_until
                        logger.warning(
                            f"MDBlist key cooldown activated for this key: {_global_window:.0f}s "
                            f"(requests paused)"
                        )
            else:
                fail_n = _rating_fail_count.get(imdb_id, 0) + 1
                _rating_fail_count[imdb_id] = fail_n
                backoff_secs = min(30 * (4 ** (fail_n - 1)), 3600.0)
                logger.warning(
                    f"Rating fetch failed for {imdb_id} (attempt {fail_n}) "
                    f"— back-off {backoff_secs:.0f}s"
                )
            _rating_backoff[imdb_id] = asyncio.get_running_loop().time() + backoff_secs
            ratings_dict   = {}
            genre          = cached_genre or _tmdb_genre
            rel            = cached_release_date
            score          = "N/A"
            keywords       = []
            award_wins     = cached_award_wins
            award_noms     = cached_award_noms
            festival_label = cached_festival_label
            age_rating     = cached_age_rating
            is_cult        = cached_is_cult
            is_true_story  = cached_is_true_story
            is_metacritic  = cached_is_metacritic
        else:
            ratings_dict, genre, rel, keywords, age_rating = rating_result
            genre = genre or _tmdb_genre

            if not rating_already_cached and not _rating_backoff_active:
                _rating_fail_count.pop(imdb_id, None)

            if isinstance(ratings_dict, dict):
                weights = (
                    effective_tv_weights
                    if type in ("tv", "series")
                    else effective_movie_weights
                )
                score = calculate_weighted_score(ratings_dict, weights)
            else:
                score = ratings_dict

            if rating_already_cached:
                award_wins     = cached_award_wins
                award_noms     = cached_award_noms
                festival_label = cached_festival_label
                age_rating     = cached_age_rating
                is_cult        = cached_is_cult
                is_true_story  = cached_is_true_story
                is_metacritic  = cached_is_metacritic
            else:
                award_wins, award_noms = parse_mdblist_awards(
                    keywords,
                    tmdb_id=tmdb_id,
                )
                kw_names = {(kw.get("name") or "").lower().strip() for kw in keywords}
                festival_label = next(
                    (label for kw, label in FESTIVAL_KEYWORDS.items() if kw in kw_names),
                    None,
                )
                is_cult       = bool({"cult-classic", "cult-film"} & kw_names)
                is_true_story = "based-on-true-story" in kw_names
                is_metacritic = "metacritic-must-see" in kw_names
                logger.info(f"Awards for {imdb_id}: wins={award_wins} noms={award_noms} "
                            f"festival={festival_label} age_rating={age_rating} "
                            f"cult={is_cult} true_story={is_true_story} metacritic={is_metacritic}")

        if not rating_failed and not rating_already_cached and effective_mdblist_key:
            set_cached_rating(
                imdb_id,
                ratings_dict if isinstance(ratings_dict, dict) else {},
                genre,
                rel,
                award_wins,
                award_noms,
                awards_fetched=True,
                festival_label=festival_label,
                age_rating=age_rating,
                is_cult=is_cult,
                is_true_story=is_true_story,
                is_metacritic=is_metacritic,
            )
            logger.info(f"Rating cached for {imdb_id}: score={score} genre={genre} "
                        f"wins={award_wins} noms={award_noms} festival={festival_label} "
                        f"age_rating={age_rating}")

        logger.info(f"Quality for {imdb_id}: tokens={quality_tokens} year={release_year}")

        discovery_meta = extract_discovery_meta(
            tmdb_data=tmdb_data,
            media_type=type,
            award_wins=award_wins,
            award_noms=award_noms,
            trending_rank=trending_rank,
            release_date=rel,
            keywords=keywords if not rating_already_cached else [],
            festival_label_override=festival_label,
            is_cult_override=is_cult,
            is_true_story_override=is_true_story,
            is_metacritic_override=is_metacritic,
            is_digital_release_override=is_digital_release(imdb_id),
        )

        if debug and debug.strip() in ("1", "true"):
            _sash_result = pick_sash(discovery_meta, rcfg.sash_priority)
            return JSONResponse({
                "imdb_id":           imdb_id,
                "tmdb_id":           tmdb_id,
                "type":              type,
                "score":             score if isinstance(score, str) else int(score),
                "genre":             genre,
                "release_year":      release_year,
                "release_date":      rel,
                "quality_tokens":    quality_tokens,
                "age_rating":        age_rating,
                "award_wins":        award_wins,
                "award_noms":        award_noms,
                "festival_label":    festival_label,
                "sash":              {"label": _sash_result[0], "type": _sash_result[1]} if _sash_result else None,
                "is_cult":           discovery_meta.is_cult,
                "is_true_story":     discovery_meta.is_true_story,
                "is_metacritic":     discovery_meta.is_metacritic_must_see,
                "is_new_release":    discovery_meta.is_new_release,
                "is_digital_release":discovery_meta.is_digital_release,
                "trending_rank":     discovery_meta.trending_rank,
                "original_language": discovery_meta.original_language,
                "matched_studios":   discovery_meta.matched_studios,
                "matched_directors": discovery_meta.matched_directors,
                "matched_cast":      discovery_meta.matched_cast,
                "sash_priority":     rcfg.sash_priority,
                "badge_display_mode":rcfg.badge_display_mode,
                "rating_display_mode":rcfg.rating_display_mode,
            })

        _bp_args = dict(
            logo=logo if (is_textless and not is_no_poster and not rcfg.textless) else None,
            fallback_title=title if is_no_poster else (title if is_textless and not logo and not rcfg.textless else None),
            discovery_meta=discovery_meta,
            quality_tokens=quality_tokens,
            release_year=release_year,
            age_rating=age_rating,
            no_poster=is_no_poster,
        )

        def _composite_and_encode() -> bytes:
            result = build_poster(image, score, genre, rcfg, **_bp_args)
            buf = io.BytesIO()
            result.convert("RGB").save(buf, format="JPEG", quality=_cfg.JPEG_QUALITY)
            return buf.getvalue()

        img_bytes = await asyncio.get_running_loop().run_in_executor(
            None, _composite_and_encode
        )

        if final_cache_key is not None and not quality_pending and not rating_failed and not _rating_backoff_active:
            set_cached_final_poster(final_cache_key, img_bytes)
            logger.info(f"Final poster cached for {final_cache_key}")

        if _render_fut is not None:
            _render_fut.set_result(img_bytes)

        response = Response(content=img_bytes, media_type="image/jpeg")
        if final_cache_key is not None:
            response.headers["ETag"] = f'"{final_cache_key}"'
        if _cfg.CDN_CACHE_TTL > 0:
            response.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
        return response

    except ValueError as exc:
        if _render_fut is not None and not _render_fut.done():
            _render_fut.set_exception(exc)
        logger.warning(f"No poster available for tmdb_id={tmdb_id}: {exc}")
        raise HTTPException(status_code=404, detail=str(exc))
    except httpx.TimeoutException as exc:
        if _render_fut is not None and not _render_fut.done():
            _render_fut.set_exception(exc)
        logger.warning(f"Upstream timeout for tmdb_id={tmdb_id}: {type(exc).__name__}")
        raise HTTPException(status_code=504, detail="Upstream request timed out")
    except httpx.HTTPStatusError as exc:
        if _render_fut is not None and not _render_fut.done():
            _render_fut.set_exception(exc)
        status = exc.response.status_code
        if status == 404:
            _endpoint = "tv" if type in ("tv", "series") else "movie"
            delete_cached_tmdb_metadata(f"{_endpoint}_{tmdb_id}")
            logger.warning(
                f"TMDB image 404 for tmdb_id={tmdb_id} — metadata cache invalidated, "
                f"will self-heal on next request"
            )
            raise HTTPException(status_code=404, detail="Poster image not found on TMDB")
        logger.error(f"Upstream HTTP {status} for tmdb_id={tmdb_id}: {exc}")
        raise HTTPException(status_code=502, detail=f"Upstream error {status}")
    except Exception as exc:
        if _render_fut is not None and not _render_fut.done():
            _render_fut.set_exception(exc)
        logger.exception(f"Error building poster for tmdb_id={tmdb_id}")
        raise HTTPException(status_code=500, detail="Failed to build poster")
    finally:
        if _rating_event_to_set is not None:
            _rating_event_to_set.set()
            _rating_fetch_inflight.pop(imdb_id, None)
        if final_cache_key is not None:
            _render_inflight.pop(final_cache_key, None)
