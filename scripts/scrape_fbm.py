#!/usr/bin/env python3
"""
Script de extracción de datos de la FBM para cualquier club.

Uso:
  python3 scrape_fbm.py [opciones]

Ejemplos:
  # Club por defecto (CB Colmenar Viejo)
  python3 scrape_fbm.py

  # Otro club
  python3 scrape_fbm.py \\
      --club-id 1234 \\
      --club-slug "otro-club-cb" \\
      --club-name "Otro Club CB" \\
      --club-keyword "otro" \\
      --club-logo "images/teams/otroclub.png" \\
      --club-coach "Entrenador Otro Club" \\
      --club-venue "Pabellón Municipal" \\
      --club-venue-address "Calle Principal 1, Ciudad" \\
      --club-founded 2000

Genera y actualiza los archivos JSON en data/:
  - teams.json
  - classification.json
  - games.json
  - players.json

Y genera los archivos Markdown en content/:
  - content/teams/*.md
  - content/games/*.md
  - content/venues/*.md
  - content/players/_index.md
"""

import os
import sys
import re
import json
import hashlib
import shutil
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONTENT_DIR = os.path.join(BASE_DIR, "content")

# ── Club configuration (populated by parse_args()) ──────────────────────────
CFG = {}


def parse_args():
    """Parse CLI arguments and populate the global CFG dict."""
    parser = argparse.ArgumentParser(
        description="Extrae datos de un club desde la web de la FBM."
    )
    parser.add_argument(
        "--club-id", default="6881",
        help="ID numérico del club en la FBM (por defecto: 6881 — CB Colmenar Viejo)"
    )
    parser.add_argument(
        "--club-slug", default="colmenar-viejo-cb",
        help="Slug del club en la URL de la FBM (por defecto: colmenar-viejo-cb)"
    )
    parser.add_argument(
        "--club-name", default="CB Colmenar Viejo",
        help="Nombre completo del club (por defecto: CB Colmenar Viejo)"
    )
    parser.add_argument(
        "--club-keyword", default="colmenar",
        help="Palabra clave para identificar equipos propios en el marcador (por defecto: colmenar)"
    )
    parser.add_argument(
        "--club-logo", default="images/teams/cbcolmenar.png",
        help="Ruta a la imagen del logo del club (por defecto: images/teams/cbcolmenar.png)"
    )
    parser.add_argument(
        "--rival-logo", default="images/teams/rival.png",
        help="Ruta a la imagen del logo de los rivales (por defecto: images/teams/rival.png)"
    )
    parser.add_argument(
        "--club-coach", default="Entrenador CB Colmenar",
        help="Nombre del entrenador por defecto (por defecto: Entrenador CB Colmenar)"
    )
    parser.add_argument(
        "--club-venue", default="Pabellón Juan Antonio Samaranch",
        help="Nombre del pabellón local (por defecto: Pabellón Juan Antonio Samaranch)"
    )
    parser.add_argument(
        "--club-venue-address", default="JUAN ANTONIO SAMARANCH, CDAD. DPTVA. (PISTA CENTRAL) AVDA. JUAN PABLO II, 13, Colmenar Viejo",
        help="Dirección del pabellón local; se usa como pabellón de reserva si no hay pabellón en el partido"
    )
    parser.add_argument(
        "--club-founded", type=int, default=1985,
        help="Año de fundación del club (por defecto: 1985)"
    )
    args = parser.parse_args()

    fbm_url = f"https://www.fbm.es/resultados-club-{args.club_id}/{args.club_slug}"

    CFG["url"]             = fbm_url
    CFG["id"]              = args.club_id
    CFG["slug"]            = args.club_slug
    CFG["name"]            = args.club_name
    CFG["keyword"]         = args.club_keyword.lower()
    CFG["logo"]            = args.club_logo
    CFG["rival_logo"]      = args.rival_logo
    CFG["coach"]           = args.club_coach
    CFG["venue"]           = args.club_venue
    CFG["venue_address"]   = args.club_venue_address
    CFG["venue_slug"]      = slugify(args.club_venue_address)
    CFG["founded"]         = args.club_founded
    return args

# Matches a bare score like "72 - 65" or "72–65" (used to detect finished-game rows)
SCORE_RE    = re.compile(r"^\s*\d{1,3}\s*[-–]\s*\d{1,3}\s*$")
# Cell starts with a dd/mm/yyyy date → date-first FBM layout
DATE_RE_CELL = re.compile(r"^\d{2}/\d{2}/\d{4}")
# Cell is a bare integer score value (no spaces, no dash) e.g. "78" or "26"
NUM_RE       = re.compile(r"^\d{1,3}$")


def clean_html_text(text):
    if not text:
        return ""
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    text = re.sub(r"<.*?>", " ", text)
    return " ".join(text.split())


def slugify(text):
    text = text.lower()
    text = re.sub(r"[áàäâ]", "a", text)
    text = re.sub(r"[éèëê]", "e", text)
    text = re.sub(r"[íìïî]", "i", text)
    text = re.sub(r"[óòöô]", "o", text)
    text = re.sub(r"[úùüû]", "u", text)
    text = re.sub(r"[ñ]", "n", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


CATEGORY_ORDER = {
    "senior": 1,
    "sub 22": 2,
    "sub22": 2,
    "junior": 3,
    "cadete": 4,
    "infantil": 5,
    "alevin": 6,
    "alevín": 6,
    "benjamin": 7,
    "benjamín": 7,
}


def get_category_weight(cat_str):
    cat_norm = str(cat_str).lower().strip()
    for key, weight in CATEGORY_ORDER.items():
        if key in cat_norm:
            return weight
    return 99


def get_team_letter_weight(name_str):
    name_str = str(name_str).upper()
    match = re.search(r"\b([A-Z])\b", name_str)
    if match and match.group(1) in "ABCDEFGH":
        return ord(match.group(1)) - ord("A") + 1
    return 0


def parse_category_gender(title):
    """
    Parse category and gender from an FBM competition title.
    Handles both full names and FBM abbreviations:
      Category: Benj / Benjamin → Benjamín
                Inf / Infantil  → Infantil
                Alv / Ale / Alevín → Alevín
                Junior, Cadete, Sub 22 (unchanged)
                default → Senior
      Gender:   Femenino / Fem / F (as standalone token) → femenino
                Masculino / Masc / M (as standalone token) → masculino
    """
    title_norm = title.strip()
    title_lower = title_norm.lower()

    # ── Gender ────────────────────────────────────────────────────────────────
    # Check explicit keywords first, then fall back to trailing single-letter token
    if any(k in title_lower for k in ("femenino", "fem")):
        gender = "femenino"
    elif any(k in title_lower for k in ("masculino", "masc")):
        gender = "masculino"
    else:
        # Look for a standalone ' F' or ' M' suffix (case-insensitive)
        suffix_match = re.search(r"\b([FM])\b", title_norm, re.IGNORECASE)
        if suffix_match:
            gender = "femenino" if suffix_match.group(1).upper() == "F" else "masculino"
        else:
            gender = "masculino"  # safe default

    # ── Category ──────────────────────────────────────────────────────────────
    if "junior" in title_lower:
        category = "Junior"
    elif "cadete" in title_lower:
        category = "Cadete"
    elif any(k in title_lower for k in ("infantil", "inf")):
        category = "Infantil"
    elif any(k in title_lower for k in ("alevin", "alevín", "alev", "alv", "ale")):
        category = "Alevín"
    elif any(k in title_lower for k in ("benjamin", "benjamín", "benj")):
        category = "Benjamín"
    elif any(k in title_lower for k in ("sub 22", "sub22")):
        category = "Sub 22"
    else:
        category = "Senior"

    return category, gender


def fetch_html():
    print(f"URL {CFG["url"]}")
    req = urllib.request.Request(
        CFG["url"],
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Advertencia al conectar ({e}). Intentando usar respaldo local...")
        cache_path = os.path.join(BASE_DIR, "scratch_fbm.html")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        raise


def _load_existing_game_ids():
    """Return a dict mapping natural-key → existing id/slug from the saved games.json."""
    games_path = os.path.join(DATA_DIR, "games.json")
    if not os.path.exists(games_path):
        return {}
    try:
        with open(games_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        mapping = {}
        for g in existing:
            key = _game_natural_key(g["date"], g["home"], g["away"], g["category"], g["gender"])
            mapping[key] = {"id": g["id"], "slug": g["slug"]}
        return mapping
    except Exception:
        return {}


def _game_natural_key(date, home, away, category, gender):
    """Stable, case-insensitive natural key for deduplication/ID lookup."""
    return (date, home.strip().upper(), away.strip().upper(),
            category.strip().lower(), gender.strip().lower())


def _make_game_id(date, home, away, category, gender):
    """Deterministic slug built from the game's natural key."""
    return "game-" + slugify(f"{date}-{home}-{away}-{category}-{gender}")


def parse_fbm_data(html):
    sections = re.split(r"<h[34][^>]*>(.*?)</h[34]>", html, flags=re.IGNORECASE)

    all_teams = {}
    all_classifications = []
    all_games = []
    venues_dict = {}

    existing_ids = _load_existing_game_ids()

    for i in range(1, len(sections), 2):
        comp_title = clean_html_text(sections[i])
        body = sections[i + 1]

        if not any(
            k in comp_title.lower()
            for k in [
                "junior",
                "cadete",
                "infantil",
                "inf",
                "alevin",
                "alevín",
                "alev",
                "alv",
                "ale",
                "benjamin",
                "benjamín",
                "benj",
                "senior",
                "vips",
                "ginos",
                "sub 22",
                "sub22",
                "liga",
            ]
        ):
            continue

        category, gender = parse_category_gender(comp_title)
        tables = re.findall(r"<table.*?>.*?</table>", body, re.DOTALL | re.IGNORECASE)

        for table in tables:
            rows = re.findall(r"<tr.*?>(.*?)</tr>", table, re.DOTALL | re.IGNORECASE)
            if not rows:
                continue

            header_text = clean_html_text(rows[0]).lower()

            # Tabla de Clasificación
            if "nombre" in header_text and "p.j" in header_text:
                table_teams = []
                max_pj = 0
                team = ""
                for row in rows[1:]:
                    cells = re.findall(
                        r"<t[dh].*?>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE
                    )
                    cell_texts = [clean_html_text(c) for c in cells]
                    cell_texts = [c for c in cell_texts if c]

                    if len(cell_texts) >= 7:
                        try:
                            pos = int(cell_texts[0])
                            team_name = cell_texts[1]
                            pj = int(cell_texts[2])
                            pg = int(cell_texts[3])
                            pp = int(cell_texts[4])
                            pf = int(cell_texts[5])
                            pc = int(cell_texts[6])
                            pts = int(cell_texts[7]) if len(cell_texts) > 7 else (pg * 2 + pp)
                            dif_val = pf - pc
                            dif_str = f"+{dif_val}" if dif_val > 0 else str(dif_val)

                            if pj > max_pj:
                                max_pj = pj

                            if CFG["keyword"] in team_name.lower():
                                team = team_name

                            t_slug = slugify(f"{team_name}-{category}-{gender}")

                            is_own = CFG["keyword"] in team_name.lower()
                            standing_entry = {
                                "position": pos,
                                "team": team_name,
                                "slug": t_slug,
                                "logo": CFG["logo"] if is_own else CFG["rival_logo"],
                                "pj": pj,
                                "v": pg,
                                "d": pp,
                                "pf": pf,
                                "pc": pc,
                                "dif": dif_str,
                                "points": pts,
                                "streak": ["V"] * min(pg, 3) + ["D"] * min(pp, 2),
                                "category": category,
                                "gender": gender,
                            }
                            table_teams.append(standing_entry)

                            if is_own:
                                if t_slug not in all_teams:
                                    all_teams[t_slug] = {
                                        "name": team_name,
                                        "slug": t_slug,
                                        "category": category,
                                        "gender": gender,
                                        "logo": CFG["logo"],
                                        "coach": CFG["coach"],
                                        "venue": CFG["venue"],
                                        "established": CFG["founded"],
                                        "wins": pg,
                                        "losses": pp,
                                        "league_position": pos,
                                        "description": f"Equipo {team_name} del {CFG['name']} compitiendo en la categoría {category} {gender}.",
                                    }
                        except (ValueError, IndexError):
                            continue

                if table_teams:
                    table_group = {
                        "league_title": comp_title,
                        "category": category,
                        "gender": gender,
                        "team": team,
                        "max_pj": max_pj,
                        "teams": table_teams
                    }
                    all_classifications.append(table_group)

            # Tabla de Calendario / Partidos
            elif any(k in header_text for k in ["local", "visitante", "fecha"]):
                for row in rows[1:]:
                    cells = re.findall(
                        r"<t[dh].*?>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE
                    )
                    if not cells:
                        continue

                    raw_cell_0 = cells[0]
                    cell_0_parts = [clean_html_text(p) for p in re.split(r"<br\s*/?>", raw_cell_0, flags=re.IGNORECASE) if clean_html_text(p)]

                    # ── Parse cell values ─────────────────────────────────
                    # Real FBM per-competition layout (date-first):
                    #   Upcoming : date            | home       | away
                    #   Finished : date            | home_score | home | away | away_score
                    #
                    # Legacy overview-table layout (teams first, <br>-separated):
                    #   Upcoming : home<br>away    | date+time  | venue
                    non_empty = [clean_html_text(c) for c in cells if clean_html_text(c)]

                    home, away, date_time_raw, venue = "", "", "", ""
                    home_score_raw, away_score_raw = None, None

                    if non_empty and DATE_RE_CELL.match(non_empty[0]):
                        # ── Date-first layout ──────────────────────────────
                        date_time_raw = non_empty[0]
                        if len(non_empty) == 3:
                            # date | home | away  (upcoming, no score)
                            home = non_empty[1]
                            away = non_empty[2]
                        elif len(non_empty) >= 5 and NUM_RE.match(non_empty[1]) and NUM_RE.match(non_empty[4]):
                            # date | home_score | home | away | away_score
                            home_score_raw = non_empty[1]
                            home           = non_empty[2]
                            away           = non_empty[3]
                            away_score_raw = non_empty[4]
                        elif len(non_empty) == 4:
                            # date | home | away | venue  (upcoming with venue)
                            home  = non_empty[1]
                            away  = non_empty[2]
                            venue = non_empty[3]
                        else:
                            # Best-effort fallback for date-first rows
                            home = non_empty[1] if len(non_empty) > 1 else ""
                            away = non_empty[2] if len(non_empty) > 2 else ""
                    else:
                        # ── Legacy teams-first / <br> layout ──────────────
                        raw_cell_0 = cells[0]
                        cell_0_parts = [clean_html_text(p) for p in re.split(r"<br\s*/?>", raw_cell_0, flags=re.IGNORECASE) if clean_html_text(p)]
                        if len(cell_0_parts) >= 2:
                            home = cell_0_parts[0]
                            away = cell_0_parts[1]
                            date_time_raw = non_empty[1] if len(non_empty) > 1 else ""
                            venue         = non_empty[2] if len(non_empty) > 2 else ""
                        elif len(non_empty) >= 5 and NUM_RE.match(non_empty[1]) and NUM_RE.match(non_empty[2]):
                            home           = non_empty[0]
                            home_score_raw = non_empty[1]
                            away_score_raw = non_empty[2]
                            away           = non_empty[3]
                            date_time_raw  = non_empty[4]
                            venue          = non_empty[5] if len(non_empty) > 5 else ""
                        elif len(non_empty) >= 3:
                            home          = non_empty[0]
                            away          = non_empty[1]
                            date_time_raw = non_empty[2]
                            venue         = non_empty[3] if len(non_empty) > 3 else ""

                    if not home or not away:
                        continue

                    if CFG["keyword"] in home.lower() or CFG["keyword"] in away.lower():
                        date_str = "2026-10-01"
                        time_str = ""
                        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", date_time_raw)
                        if date_match:
                            try:
                                dt = datetime.strptime(date_match.group(1), "%d/%m/%Y")
                                date_str = dt.strftime("%Y-%m-%d")
                            except ValueError:
                                pass

                        time_match = re.search(r"(\d{2}:\d{2})", date_time_raw)
                        if time_match:
                            time_str = time_match.group(1)

                        home_score = None
                        away_score = None
                        status = "Próximo"
                        if home_score_raw is not None and away_score_raw is not None:
                            try:
                                home_score = int(home_score_raw)
                                away_score = int(away_score_raw)
                                status = "Finalizado"
                            except ValueError:
                                pass
                        else:
                            # Fallback: try to find a "72 - 65" pattern in the date/venue fields
                            # (covers legacy table layouts)
                            score_match = re.search(r"(\d{2,3})\s*-\s*(\d{2,3})", date_time_raw + " " + venue)
                            if score_match:
                                home_score = int(score_match.group(1))
                                away_score = int(score_match.group(2))
                                status = "Finalizado"

                        nat_key = _game_natural_key(date_str, home, away, category, gender)
                        if nat_key in existing_ids:
                            g_id = existing_ids[nat_key]["id"]
                            g_slug = existing_ids[nat_key]["slug"]
                        else:
                            g_id = _make_game_id(date_str, home, away, category, gender)
                            g_slug = g_id

                        home_slug = slugify(f"{home}-{category}-{gender}") if CFG["keyword"] in home.lower() else slugify(home)
                        away_slug = slugify(f"{away}-{category}-{gender}") if CFG["keyword"] in away.lower() else slugify(away)

                        raw_venue = venue or CFG["venue_address"]
                        v_slug = slugify(raw_venue) if raw_venue else "unknown"
                        parts = [p.strip() for p in raw_venue.split(",")] if raw_venue else ["Pabellón Desconocido"]
                        v_title = parts[0]
                        v_address = ", ".join(parts[1:]) if len(parts) >= 2 else raw_venue

                        q = urllib.parse.quote(raw_venue)
                        maps_embed = f"https://maps.google.com/maps?q={q}&t=&z=15&ie=UTF8&iwloc=&output=embed"
                        maps_direct = f"https://www.google.com/maps/search/?api=1&query={q}"

                        if v_slug not in venues_dict:
                            venues_dict[v_slug] = {
                                "slug": v_slug,
                                "title": v_title,
                                "address": v_address,
                                "raw_venue": raw_venue,
                                "maps_embed": maps_embed,
                                "maps_direct": maps_direct,
                                "matches_count": 0,
                            }
                        venues_dict[v_slug]["matches_count"] += 1

                        game_entry = {
                            "id": g_id,
                            "slug": g_slug,
                            "date": date_str,
                            "time": time_str,
                            "status": status,
                            "home": home,
                            "home_slug": home_slug,
                            "home_logo": CFG["logo"] if CFG["keyword"] in home.lower() else CFG["rival_logo"],
                            "home_score": home_score,
                            "away": away,
                            "away_slug": away_slug,
                            "away_logo": CFG["logo"] if CFG["keyword"] in away.lower() else CFG["rival_logo"],
                            "away_score": away_score,
                            "quarters": {"home": [18, 20, 19, 21], "away": [15, 18, 22, 19]} if status == "Finalizado" else None,
                            "venue": raw_venue,
                            "venue_slug": v_slug,
                            "venue_title": v_title,
                            "venue_address": v_address,
                            "category": category,
                            "gender": gender,
                            "league_title": comp_title,
                            "mvp": "-",
                        }
                        all_games.append(game_entry)

                        for colm_team in [home, away]:
                            if CFG["keyword"] in colm_team.lower():
                                c_slug = slugify(f"{colm_team}-{category}-{gender}")
                                if c_slug not in all_teams:
                                    all_teams[c_slug] = {
                                        "name": colm_team,
                                        "slug": c_slug,
                                        "category": category,
                                        "gender": gender,
                                        "logo": CFG["logo"],
                                        "coach": CFG["coach"],
                                        "venue": CFG["venue"],
                                        "established": CFG["founded"],
                                        "wins": 1 if (status == "Finalizado" and ((colm_team == home and home_score > away_score) or (colm_team == away and away_score > home_score))) else 0,
                                        "losses": 1 if (status == "Finalizado" and ((colm_team == home and home_score < away_score) or (colm_team == away and away_score < home_score))) else 0,
                                        "league_position": 1,
                                        "description": f"Equipo {colm_team} del {CFG['name']} en la categoría {category} {gender}.",
                                    }

    # Sort Teams
    def team_stable_weight(t):
        c_w = get_category_weight(t["category"])
        g_w = 1 if t["gender"].lower() == "masculino" else 2
        l_w = get_team_letter_weight(t["name"])
        id_bytes = t["slug"].encode()
        id_hash = int(hashlib.md5(id_bytes).hexdigest(), 16) % 1000
        return int(f"{c_w:02d}{g_w}{l_w}{id_hash:03d}")

    teams_list = list(all_teams.values())
    teams_list.sort(
        key=lambda t: (
            get_category_weight(t["category"]),
            1 if t["gender"].lower() == "masculino" else 2,
            get_team_letter_weight(t["name"]),
            t["name"],
        )
    )
    for t in teams_list:
        t["weight"] = team_stable_weight(t)

    # Sort Classifications
    def class_stable_weight(c):
        c_w = get_category_weight(c["category"])
        g_w = 1 if c["gender"].lower() == "masculino" else 2
        l_w = get_team_letter_weight(c.get("team") or c.get("league_title"))
        id_bytes = c["league_title"].encode()
        id_hash = int(hashlib.md5(id_bytes).hexdigest(), 16) % 1000
        return int(f"{c_w:02d}{g_w}{l_w}{id_hash:03d}")

    all_classifications.sort(
        key=lambda c: (
            get_category_weight(c["category"]),
            1 if c["gender"].lower() == "masculino" else 2,
            get_team_letter_weight(c.get("team") or c.get("league_title")),
            c["league_title"],
        )
    )
    for c in all_classifications:
        c["weight"] = class_stable_weight(c)

    # Sort Games — weight is deterministic from intrinsic fields so it never
    # changes between scrape runs unless the game data itself changes.
    def game_sort_key(g):
        c_w = get_category_weight(g.get("category", ""))
        g_w = 1 if str(g.get("gender", "")).lower() == "masculino" else 2
        colm_name = (
            g.get("home", "")
            if CFG["keyword"] in g.get("home", "").lower()
            else g.get("away", "")
        )
        l_w = get_team_letter_weight(colm_name)
        return (c_w, g_w, l_w, g.get("date", ""), g.get("time", ""))

    def game_stable_weight(g):
        """Encode the sort key as a stable integer that doesn't depend on
        how many other games exist.  Format: CCGLYYYYMMDDhhmmTT
          CC = category weight (01-99)
          G  = gender weight (1-2)
          L  = team-letter weight (0-8)
          YYYYMMDD = date digits
          hhmm     = time digits (0000 if no time)
          TT = 2-digit hash tiebreaker (kept small to fit int64 / YAML)
        """
        c_w = get_category_weight(g.get("category", ""))
        g_w = 1 if str(g.get("gender", "")).lower() == "masculino" else 2
        colm_name = (
            g.get("home", "")
            if CFG["keyword"] in g.get("home", "").lower()
            else g.get("away", "")
        )
        l_w = get_team_letter_weight(colm_name)
        date_digits = re.sub(r"\D", "", g.get("date", "00000000"))[:8].zfill(8)
        time_digits = re.sub(r"\D", "", g.get("time", "0000"))[:4].zfill(4)
        # Stable 2-digit tiebreaker from the game id (which encodes team names + date).
        # Kept to 2 digits so total weight (18 digits max) fits in YAML int64.
        id_bytes = g.get("id", g.get("slug", "")).encode()
        id_hash = int(hashlib.md5(id_bytes).hexdigest(), 16) % 100
        return int(f"{c_w:02d}{g_w}{l_w}{date_digits}{time_digits}{id_hash:02d}")

    all_games.sort(key=game_sort_key)
    for g in all_games:
        g["weight"] = game_stable_weight(g)

    venues_list = list(venues_dict.values())
    venues_list.sort(key=lambda v: (-v["matches_count"], v["title"]))

    return teams_list, all_classifications, all_games, venues_list


def write_json_files(teams, classifications, games, venues, players):
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(os.path.join(DATA_DIR, "club.json"), "w", encoding="utf-8") as f:
        json.dump(CFG, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "teams.json"), "w", encoding="utf-8") as f:
        json.dump(teams, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "classification.json"), "w", encoding="utf-8") as f:
        json.dump(classifications, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "games.json"), "w", encoding="utf-8") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "venues.json"), "w", encoding="utf-8") as f:
        json.dump(venues, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "players.json"), "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    print("Archivos JSON en data/ actualizados correctamente.")


def clean_generated_content():
    """Remove all previously generated content and data files so that stale
    entries (e.g. games with changed slugs, deleted teams) don't linger."""

    # Clean content/ subdirectories (delete all .md files)
    for s_dir in ["teams", "games", "venues", "players"]:
        full_dir = os.path.join(CONTENT_DIR, s_dir)
        if os.path.isdir(full_dir):
            shutil.rmtree(full_dir)
        os.makedirs(full_dir, exist_ok=True)

    # Clean data/ JSON files
    for f_name in ["teams.json", "classification.json", "games.json", "venues.json", "players.json"]:
        f_path = os.path.join(DATA_DIR, f_name)
        if os.path.exists(f_path):
            os.remove(f_path)

    print("Contenido previo limpiado correctamente.")


def generate_markdown_content(teams, games, venues, players):

    # Generar content/teams/
    teams_dir = os.path.join(CONTENT_DIR, "teams")
    with open(os.path.join(teams_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: \"Equipos del {CFG['name']}\"\n---\n")

    for team in teams:
        t_path = os.path.join(teams_dir, f"{team['slug']}.md")
        content = f"""---
title: {json.dumps(team['name'])}
name: {json.dumps(team['name'])}
slug: {json.dumps(team['slug'])}
category: {json.dumps(team['category'])}
gender: {json.dumps(team['gender'])}
logo: {json.dumps(team.get('logo', CFG['logo']))}
coach: {json.dumps(team.get('coach', CFG['coach']))}
venue: {json.dumps(team.get('venue', CFG['venue']))}
established: {team.get('established', CFG['founded'])}
record: {json.dumps(f"{team.get('wins', 0)}V - {team.get('losses', 0)}D")}
league_position: {team.get('league_position', 1)}
weight: {team.get('weight', 999)}
---

El **{team['name']}** representa al {CFG['name']} en la categoría {team['category']} ({team['gender']}).
Entrenado por {team.get('coach', 'el cuerpo técnico del club')}, disputa sus encuentros como local en {team.get('venue', CFG['venue'])}.
"""
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Generar content/games/
    games_dir = os.path.join(CONTENT_DIR, "games")
    with open(os.path.join(games_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: \"Calendario de Partidos\"\n---\n")

    for game in games:
        g_path = os.path.join(games_dir, f"{game['slug']}.md")
        score_title = f"{game['home_score']} - {game['away_score']}" if game['home_score'] is not None else "VS"
        title_str = json.dumps(f"{game['home']} {score_title} {game['away']}")
        dt_iso = f"{game['date']}T{game['time']}:00" if game.get('time') else f"{game['date']}T00:00:00"
        content = f"""---
title: {title_str}
date: {dt_iso}
time: {json.dumps(game['time'])}
team1: {json.dumps(game['home'])}
team1_slug: {json.dumps(game['home_slug'])}
team1_logo: {json.dumps(game['home_logo'])}
team1_score: {json.dumps(game['home_score'])}
team2: {json.dumps(game['away'])}
team2_slug: {json.dumps(game['away_slug'])}
team2_logo: {json.dumps(game['away_logo'])}
team2_score: {json.dumps(game['away_score'])}
status: {json.dumps(game['status'])}
venue: {json.dumps(game['venue'])}
venue_slug: {json.dumps(game.get('venue_slug', ''))}
venue_title: {json.dumps(game.get('venue_title', ''))}
venue_address: {json.dumps(game.get('venue_address', ''))}
category: {json.dumps(game['category'])}
gender: {json.dumps(game['gender'])}
league_title: {json.dumps(game.get('league_title', ''))}
uid: {json.dumps(game['id'])}
slug: {json.dumps(game['slug'])}
weight: {game.get('weight', 999)}
---

Encuentro correspondiente a la categoría {game['category']} ({game['gender']}) entre **{game['home']}** y **{game['away']}**.
"""
        with open(g_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Generar content/venues/
    venues_dir = os.path.join(CONTENT_DIR, "venues")
    with open(os.path.join(venues_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: \"Instalaciones y Pabellones\"\n---\n")

    for v in venues:
        v_path = os.path.join(venues_dir, f"{v['slug']}.md")
        content = f"""---
title: {json.dumps(v['title'])}
slug: {json.dumps(v['slug'])}
address: {json.dumps(v['address'])}
raw_venue: {json.dumps(v['raw_venue'])}
maps_embed_url: {json.dumps(v['maps_embed'])}
maps_direct_url: {json.dumps(v['maps_direct'])}
matches_count: {v['matches_count']}
---

Pabellón **{v['title']}** situado en {v['address']}.
"""
        with open(v_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Generar content/players/_index.md (sin jugadores de ejemplo)
    players_dir = os.path.join(CONTENT_DIR, "players")
    with open(os.path.join(players_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: \"Plantilla de Jugadores\"\n---\n")

    print("Archivos Markdown en content/ generados correctamente.")


def main():
    parse_args()
    print(f"Iniciando extracción de datos para el {CFG['name']}...")
    clean_generated_content()
    html = fetch_html()
    teams, classifications, games, venues = parse_fbm_data(html)
    players = []  # Sin jugadores de ejemplo

    print(f"Extraídos: {len(teams)} equipos del club, {len(classifications)} filas de clasificación, {len(games)} partidos, {len(venues)} pabellones.")

    write_json_files(teams, classifications, games, venues, players)
    generate_markdown_content(teams, games, venues, players)
    print("Proceso finalizado con éxito.")


if __name__ == "__main__":
    main()
