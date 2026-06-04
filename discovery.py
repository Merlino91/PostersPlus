#discovery.py
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime

from config import SASH_PRIORITY as DEFAULT_SASH_PRIORITY

logger = logging.getLogger(__name__)

NOTABLE_STUDIOS: dict[str, str] = {
    "A24": "A24 Films", "Pixar": "Pixar Studio", "Studio Ghibli": "Studio Ghibli",
    "Blumhouse Productions": "Blumhouse", "Neon": "NEON Rated", "Searchlight Pictures": "SL Pictures",
    "BBC Films": "BBC Films", "Bad Robot": "Bad Robot", "HBO": "HBO Original", "Laika Entertainment": "Laika",
}

NOTABLE_DIRECTORS: dict[str, str] = {
    "Christopher Nolan": "C. Nolan", "Denis Villeneuve": "D. Villeneuve", "Martin Scorsese": "M. Scorsese",
    "Wes Anderson": "Wes Anderson", "Sofia Coppola": "S. Coppola", "Bong Joon-ho": "B. Joon-ho",
    "Hayao Miyazaki": "H. Miyazaki", "David Fincher": "D. Fincher", "Paul Thomas Anderson":"P.T. Anderson",
    "Quentin Tarantino": "Q. Tarantino", "Alfonso Cuarón": "A. Cuarón", "Guillermo del Toro": "G. del Toro",
    "Ridley Scott": "R. Scott", "Steven Spielberg": "S. Spielberg", "Joel Coen": "Coen Brothers",
    "Ethan Coen": "Coen Brothers", "David Lynch": "D. Lynch", "Darren Aronofsky": "D. Aronofsky",
    "Yorgos Lanthimos": "Y. Lanthimos", "Ari Aster": "Ari Aster", "Jordan Peele": "J. Peele",
    "Greta Gerwig": "G. Gerwig", "Robert Eggers": "R. Eggers", "Céline Sciamma": "C. Sciamma",
    "Park Chan-wook": "P. Chan-wook", "Wong Kar-wai": "Wong Kar-wai", "Hirokazu Kore-eda": "H. Kore-eda",
    "Luca Guadagnino": "L. Guadagnino", "Sean Baker": "Sean Baker", "Stanley Kubrick": "S. Kubrick",
    "Spike Lee": "Spike Lee", "David Cronenberg": "D. Cronenberg", "Michael Mann": "Michael Mann",
    "Francis Ford Coppola":"F.F Coppola", "Jane Campion": "J. Campion", "Terrence Malick": "T. Malick",
    "Mike Flanagan": "M. Flanagan", "James Cameron": "J. Cameron", "Peter Jackson": "P. Jackson",
}

NOTABLE_CAST: dict[str, str] = {
    "Cate Blanchett": "Cate Blanchett", "Meryl Streep": "Meryl Streep", "Viola Davis": "Viola Davis",
    "Tilda Swinton": "Tilda Swinton", "Joaquin Phoenix": "Joaquin Phoenix", "Daniel Day-Lewis": "D. Day-Lewis",
    "Tom Hanks": "Tom Hanks", "Denzel Washington": "D. Washington", "Leonardo DiCaprio": "L. DiCaprio",
    "Natalie Portman": "Natalie Portman", "Nicole Kidman": "Nicole Kidman", "Julianne Moore": "Julianne Moore",
    "Jessica Lange": "Jessica Lange", "Anthony Hopkins": "Anthony Hopkins", "Gary Oldman": "Gary Oldman",
    "Ryan Gosling": "Ryan Gosling", "Margot Robbie": "Margot Robbie", "Adam Driver": "Adam Driver",
    "Saoirse Ronan": "Saoirse Ronan", "Oscar Isaac": "Oscar Isaac", "Mahershala Ali": "Mahershala Ali",
    "Lupita Nyong'o": "Lupita Nyong'o", "Pedro Pascal": "Pedro Pascal", "Jeff Bridges": "Jeff Bridges",
    "Charlize Theron": "Charlize Theron", "Timothée Chalamet": "T. Chalamet", "Zendaya": "Zendaya",
    "Florence Pugh": "Florence Pugh", "Austin Butler": "Austin Butler", "Barry Keoghan": "Barry Keoghan",
    "Paul Mescal": "Paul Mescal", "Carey Mulligan": "Carey Mulligan", "Andrew Garfield": "Andrew Garfield",
    "Ana de Armas": "Ana de Armas", "Anya Taylor-Joy": "Anya Taylor-Joy", "Frances McDormand": "F. McDormand",
    "Robert De Niro": "Robert De Niro", "Al Pacino": "Al Pacino", "Willem Dafoe": "Willem Dafoe",
    "Philip Seymour Hoffman": "P. Hoffman", "Jake Gyllenhaal": "Jake Gyllenhaal", "Emma Stone": "Emma Stone",
    "Christian Bale": "Christian Bale", "Colin Farrell": "Colin Farrell", "Rachel McAdams": "Rachel McAdams",
    "Amy Adams": "Amy Adams", "Jeremy Strong": "Jeremy Strong", "Ayo Edebiri": "Ayo Edebiri",
    "Kieran Culkin": "Kieran Culkin", "Jeremy Allen White": "J. White", "Mia Goth": "Mia Goth",
    "Sebastian Stan": "Sebastian Stan", "Harris Dickinson": "H. Dickinson", "Mikey Madison": "Mikey Madison",
    "Josh O'Connor": "Josh O'Connor",
}

_STRUCTURAL_CHECKS = ["short_film", "mini_series", "binge_ready"]
_STRUCTURAL_LABELS: dict[str, str] = { "short_film": "Cortometraggio", "mini_series": "Mini Serie", "binge_ready": "Da Fare Maratona" }

FESTIVAL_KEYWORDS: dict[str, str] = { 
    "festival-cannes-winner": "Palme d'Or", "festival-venice-winner": "Golden Lion", "festival-berlin-winner": "Golden Bear",
    "festival-toronto-winner": "People's Choice", "festival-sundance-winner": "Sundance GJ", "festival-busan-winner": "New Currents",
    "festival-locarno-winner": "Golden Leopard", "festival-rotterdam-winner": "Tiger Award", "festival-sxsw-winner": "SXSW Jury",
    "festival-tribeca-winner": "Tribeca AA",
}

LANGUAGE_LABELS: dict[str, str] = {
    "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "da": "Danish", "sv": "Swedish",
    "no": "Norwegian", "fi": "Finnish", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "tr": "Turkish", "ar": "Arabic", "hi": "Hindi", "fa": "Persian", "ro": "Romanian",
    "hu": "Hungarian", "cs": "Czech", "he": "Hebrew", "el": "Greek",
}

# NUOVO: Aggiunti i nuovi tag dinamici e assegnati alle loro famiglie di colore
_SASH_TYPES: dict[str, str] = {
    "next_episode":    "trending",  # Usa i toni dell'azzurro
    "finale":          "win",       # Usa i toni dell'oro
    "returning":       "info",      # Usa i toni del verde acqua
    "ended":           "nom",       # Usa i toni del grigio
    "upcoming":        "trending",  
    "wins":            "win",       
    "gg_wins":         "win",       
    "pic_noms":        "nom",       
    "gg_noms":         "nom",       
    "emmy_noms":       "nom",       
    "festival":        "win",       
    "studio":          "prestige",  
    "director":        "prestige",  
    "cast":            "cast",      
    "trending":        "trending",  
    "cult":            "trending",  
    "foreign":         "info",      
    "new_release":     "info",      
    "digital_release": "info",      
    "metacritic":      "nom",       
    "true_story":      "info",      
    "structural":      "info",      
}

NEW_RELEASE_DAYS = 14

def _is_recent(release_date: str | None) -> bool:
    if not release_date: return False
    try: return (date.today() - datetime.strptime(release_date, "%Y-%m-%d").date()).days <= NEW_RELEASE_DAYS
    except ValueError: return False

@dataclass
class DiscoveryMeta:
    award_wins: list[str] = field(default_factory=list)
    award_noms: list[str] = field(default_factory=list)
    matched_studios: list[str] = field(default_factory=list)
    matched_directors: list[str] = field(default_factory=list)
    matched_cast: list[str] = field(default_factory=list)
    festival_label: str | None = None
    is_short_film: bool = False
    is_mini_series: bool = False
    is_binge_ready: bool = False
    original_language: str | None = None
    trending_rank: int | None = None
    is_new_release: bool = False
    is_cult: bool = False
    is_true_story: bool = False
    is_metacritic_must_see: bool = False
    is_digital_release: bool = False
    status: str | None = None
    next_episode_to_air: str | None = None
    release_date: str | None = None


def extract_discovery_meta(
    tmdb_data: dict, media_type: str, award_wins: list[str], award_noms: list[str], trending_rank: int | None,
    *, release_date: str | None = None, keywords: list[dict] | None = None, festival_label_override: str | None = None,
    is_cult_override: bool | None = None, is_true_story_override: bool | None = None, is_metacritic_override: bool | None = None,
    is_digital_release_override: bool | None = None, notable_studios: dict[str, str] | None = None,
    notable_directors: dict[str, str] | None = None, notable_cast: dict[str, str] | None = None,
    festival_keywords: dict[str, str] | None = None, language_labels: dict[str, str] | None = None,
) -> DiscoveryMeta:
    studios = notable_studios or NOTABLE_STUDIOS
    directors = notable_directors or NOTABLE_DIRECTORS
    cast_list = notable_cast or NOTABLE_CAST
    fest_keywords = festival_keywords or FESTIVAL_KEYWORDS

    meta = DiscoveryMeta(
        award_wins=award_wins, award_noms=award_noms, trending_rank=trending_rank,
        original_language=tmdb_data.get("original_language"), status=tmdb_data.get("status"),
        next_episode_to_air=tmdb_data.get("next_episode_to_air"), release_date=release_date
    )

    keyword_names: set[str] = ({(kw.get("name") or "").lower().strip() for kw in keywords} if keywords else set())

    if festival_label_override is not None: meta.festival_label = festival_label_override
    elif keyword_names:
        for kw_name, label in fest_keywords.items():
            if kw_name in keyword_names: meta.festival_label = label; break

    if is_cult_override is not None: meta.is_cult = is_cult_override
    elif keyword_names: meta.is_cult = bool({"cult-classic", "cult-film"} & keyword_names)

    if is_true_story_override is not None: meta.is_true_story = is_true_story_override
    elif keyword_names: meta.is_true_story = "based-on-true-story" in keyword_names

    if is_metacritic_override is not None: meta.is_metacritic_must_see = is_metacritic_override
    elif keyword_names: meta.is_metacritic_must_see = "metacritic-must-see" in keyword_names

    if is_digital_release_override is not None: meta.is_digital_release = is_digital_release_override

    for company in tmdb_data.get("production_companies", []):
        name = company.get("name", "")
        if name in studios: meta.matched_studios.append(studios[name])

    credits = tmdb_data.get("credits", {})
    for crew_member in credits.get("crew", []):
        if crew_member.get("job") == "Director":
            name = crew_member.get("name", "")
            if name in directors and directors[name] not in meta.matched_directors: meta.matched_directors.append(directors[name])

    for cast_member in credits.get("cast", [])[:10]:
        name = cast_member.get("name", "")
        if name in cast_list: meta.matched_cast.append(cast_list[name])

    is_tv = media_type in ("tv", "series")
    if not is_tv:
        runtime = tmdb_data.get("runtime") or 0
        meta.is_short_film = 0 < runtime < 40
    else:
        num_seasons = tmdb_data.get("number_of_seasons") or 0
        num_episodes = tmdb_data.get("number_of_episodes") or 0
        meta.is_mini_series = (num_seasons == 1 and 0 < num_episodes <= 8)
        if num_seasons >= 3 and num_episodes > 0:
            meta.is_binge_ready = 6 <= (num_episodes / num_seasons) <= 20

    if _is_recent(release_date): meta.is_new_release = True
    return meta

def pick_sash(meta: DiscoveryMeta, priority: list[str]) -> tuple[str, str] | None:
    for slot in priority:
        result = _evaluate_slot(slot, meta)
        if result is not None: return result, _SASH_TYPES.get(slot, "info")
    return None

MONTHS_IT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
def _format_date_it(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        art = "l'" if d.day in (1, 8, 11) else "il "
        return f"{art}{d.day} {MONTHS_IT[d.month - 1]}"
    except ValueError: return date_str

def _is_future(date_str: str) -> bool:
    try: return datetime.strptime(date_str, "%Y-%m-%d").date() > date.today()
    except ValueError: return False

def _evaluate_slot(slot: str, meta: DiscoveryMeta) -> str | None:
    # NUOVO: Gestione intelligente dei nuovi Sash Dinamici
    if slot == "next_episode":
        if meta.next_episode_to_air and _is_future(meta.next_episode_to_air):
            return f"Prossimo Ep: {_format_date_it(meta.next_episode_to_air)}"
        return None
    if slot == "finale":
        if meta.status == "Ended": return "Stagione Finale"
        return None
    if slot == "returning":
        if meta.status == "Returning Series": return "In Corso (Serie Attiva)"
        return None
    if slot == "ended":
        if meta.status == "Ended": return "Serie Terminata"
        return None

    if slot == "upcoming":
        if meta.next_episode_to_air and _is_future(meta.next_episode_to_air):
            return f"Nuovo Ep. {_format_date_it(meta.next_episode_to_air)}"
        if meta.status and meta.status not in ("Released", "Ended", "Canceled", "Rumored"):
            if meta.release_date and _is_future(meta.release_date):
                return f"In arrivo {_format_date_it(meta.release_date)}"
            return "Prossimamente"
        if meta.release_date and _is_future(meta.release_date):
            return f"In arrivo {_format_date_it(meta.release_date)}"
        return None

    if slot == "wins":
        w = [v for v in meta.award_wins if v != "Golden Globe"]
        return w[0] if w else None
    if slot == "gg_wins": return "Golden Globe" if "Golden Globe" in meta.award_wins else None
    if slot in ("pic_noms", "emmy_noms"): return next((n for n in meta.award_noms if "Best Picture" in n or "Emmy" in n), None)
    if slot == "gg_noms": return "Golden Globe" if "Golden Globe" in meta.award_noms else None
    if slot == "noms": return " • ".join(meta.award_noms) if meta.award_noms else None
    if slot == "festival": return meta.festival_label if meta.festival_label else None
    if slot == "foreign":
        lang = meta.original_language
        if not lang or lang == "en": return None
        return LANGUAGE_LABELS.get(lang, "Lingua Originale")
    if slot == "studio": return f"{meta.matched_studios[0]}" if meta.matched_studios else None
    if slot == "director": return f"{meta.matched_directors[0]}" if meta.matched_directors else None
    if slot == "cast": return meta.matched_cast[0] if meta.matched_cast else None
    if slot == "trending": return f"#{meta.trending_rank} Today" if meta.trending_rank else None
    if slot in ("new_release", "digital_release"):
        if meta.is_new_release or meta.is_digital_release: return "Nuovi Episodi"
        return None
    if slot == "metacritic": return "Da Non Perdere" if meta.is_metacritic_must_see else None
    if slot == "cult": return "Cult Classic" if meta.is_cult else None
    if slot == "true_story": return "Tratto da una storia vera" if meta.is_true_story else None
    if slot == "structural":
        for key in _STRUCTURAL_CHECKS:
            if key == "short_film"  and meta.is_short_film:  return _STRUCTURAL_LABELS[key]
            if key == "mini_series" and meta.is_mini_series:  return _STRUCTURAL_LABELS[key]
            if key == "binge_ready" and meta.is_binge_ready:  return _STRUCTURAL_LABELS[key]
        return None
    return None

# NUOVO: Aggiunti i nuovi ID alla whitelist di sicurezza
ALL_PRIORITY_SLOTS: list[str] = [
    "next_episode", "finale", "returning", "ended", 
    "upcoming", "wins", "gg_wins", "festival", "pic_noms", "gg_noms", "studio", "director",
    "cast", "trending", "cult", "foreign", "new_release", "metacritic", "true_story",
    "structural", "emmy_noms", "digital_release", "noms",
]

_OVERRIDE_PATH = os.environ.get("DISCOVERY_OVERRIDES_PATH", "/app/cache/discovery_overrides.json")

def _load_discovery_overrides() -> None:
    try:
        with open(_OVERRIDE_PATH, encoding="utf-8") as fh: data = json.load(fh)
    except FileNotFoundError: return                        
    except Exception as exc: return

    if not isinstance(data, dict): return
    mode = data.get("mode", "replace")
    studios_raw = data.get("studios"); dirs_raw = data.get("directors"); cast_raw = data.get("cast")
    if mode == "merge":
        if isinstance(studios_raw, dict): NOTABLE_STUDIOS.update(studios_raw)
        if isinstance(dirs_raw, dict): NOTABLE_DIRECTORS.update(dirs_raw)
        if isinstance(cast_raw, dict): NOTABLE_CAST.update(cast_raw)
    else:
        if isinstance(studios_raw, dict): NOTABLE_STUDIOS.clear(); NOTABLE_STUDIOS.update(studios_raw)
        if isinstance(dirs_raw, dict): NOTABLE_DIRECTORS.clear(); NOTABLE_DIRECTORS.update(dirs_raw)
        if isinstance(cast_raw, dict): NOTABLE_CAST.clear(); NOTABLE_CAST.update(cast_raw)

_load_discovery_overrides()
