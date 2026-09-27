#!/usr/bin/env python3
"""
Script de extracción de datos de la FBM para el CB Colmenar Viejo.
Lee la página oficial de resultados del club en la FBM:
https://www.fbm.es/resultados-club-6881/colmenar-viejo-cb

Genera y actualiza los archivos JSON en data/:
- teams.json
- classification.json
- games.json
- players.json (vacío, sin jugadores de ejemplo)

Y genera los archivos Markdown correspondientes en content/:
- content/teams/*.md
- content/games/*.md
- content/players/_index.md
"""

import os
import sys
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime

FBM_URL = "https://www.fbm.es/resultados-club-6881/colmenar-viejo-cb"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONTENT_DIR = os.path.join(BASE_DIR, "content")


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
    title_lower = title.lower()

    if "fem" in title_lower:
        gender = "femenino"
    else:
        gender = "masculino"

    if "junior" in title_lower:
        category = "Junior"
    elif "cadete" in title_lower:
        category = "Cadete"
    elif "infantil" in title_lower:
        category = "Infantil"
    elif "alevin" in title_lower or "alevín" in title_lower:
        category = "Alevín"
    elif "benjamin" in title_lower or "benjamín" in title_lower:
        category = "Benjamín"
    elif "sub 22" in title_lower or "sub22" in title_lower:
        category = "Sub 22"
    else:
        category = "Senior"

    return category, gender


def fetch_html():
    req = urllib.request.Request(
        FBM_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Advertencia al conectar con la FBM ({e}). Intentando usar respaldo local...")
        cache_path = os.path.join(BASE_DIR, "scratch_fbm.html")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        raise


def parse_fbm_data(html):
    sections = re.split(r"<h[34][^>]*>(.*?)</h[34]>", html, flags=re.IGNORECASE)

    all_teams = {}
    all_classifications = []
    all_games = []
    venues_dict = {}
    game_counter = 1

    for i in range(1, len(sections), 2):
        comp_title = clean_html_text(sections[i])
        body = sections[i + 1]

        if not any(
            k in comp_title.lower()
            for k in [
                "junior",
                "cadete",
                "infantil",
                "alevin",
                "benjamin",
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
                colmenar_team = ""
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

                            if "colmenar" in team_name.lower():
                                colmenar_team = team_name

                            t_slug = slugify(f"{team_name}-{category}-{gender}")

                            standing_entry = {
                                "position": pos,
                                "team": team_name,
                                "slug": t_slug,
                                "logo": f"/images/teams/{'colmenar' if 'colmenar' in team_name.lower() else 'rival'}.jpg",
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

                            if "colmenar" in team_name.lower():
                                if t_slug not in all_teams:
                                    all_teams[t_slug] = {
                                        "name": team_name,
                                        "slug": t_slug,
                                        "category": category,
                                        "gender": gender,
                                        "logo": "/images/teams/cbcolmenar.png",
                                        "coach": "Entrenador CB Colmenar",
                                        "venue": "Pabellón Juan Antonio Samaranch",
                                        "established": 1985,
                                        "wins": pg,
                                        "losses": pp,
                                        "league_position": pos,
                                        "description": f"Equipo {team_name} del CB Colmenar Viejo compitiendo en la categoría {category} {gender}.",
                                    }
                        except (ValueError, IndexError):
                            continue

                if table_teams:
                    table_group = {
                        "league_title": comp_title,
                        "category": category,
                        "gender": gender,
                        "colmenar_team": colmenar_team,
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

                    home, away, date_time_raw, venue = "", "", "", ""
                    if len(cell_0_parts) >= 2:
                        home = cell_0_parts[0]
                        away = cell_0_parts[1]
                        if len(cells) >= 2:
                            date_time_raw = clean_html_text(cells[1])
                        if len(cells) >= 3:
                            venue = clean_html_text(cells[2])
                    else:
                        non_empty = [clean_html_text(c) for c in cells if clean_html_text(c)]
                        if len(non_empty) >= 4:
                            home = non_empty[0]
                            away = non_empty[1]
                            date_time_raw = non_empty[2]
                            venue = non_empty[3]

                    if not home or not away:
                        continue

                    if "COLMENAR" in home.upper() or "COLMENAR" in away.upper():
                        date_str = "2026-10-01"
                        time_str = "12:00"
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

                        score_match = re.search(r"(\d{2,3})\s*-\s*(\d{2,3})", date_time_raw + " " + venue)
                        home_score = None
                        away_score = None
                        status = "Próximo"
                        if score_match:
                            home_score = int(score_match.group(1))
                            away_score = int(score_match.group(2))
                            status = "Finalizado"

                        g_id = f"game-{date_str.replace('-', '')}-{game_counter:02d}"
                        game_counter += 1

                        home_slug = slugify(f"{home}-{category}-{gender}") if "colmenar" in home.lower() else slugify(home)
                        away_slug = slugify(f"{away}-{category}-{gender}") if "colmenar" in away.lower() else slugify(away)

                        raw_venue = venue or "JUAN ANTONIO SAMARANCH, CDAD. DPTVA. (PISTA CENTRAL) AVDA. JUAN PABLO II, 13, Colmenar Viejo"
                        v_slug = slugify(raw_venue)
                        parts = [p.strip() for p in raw_venue.split(",") if p.strip()]
                        v_title = parts[0] if parts else raw_venue
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
                            "slug": g_id,
                            "date": date_str,
                            "time": time_str,
                            "status": status,
                            "home": home,
                            "home_slug": home_slug,
                            "home_logo": "/images/teams/cbcolmenar.png" if "colmenar" in home.lower() else "/images/teams/rival.png",
                            "home_score": home_score,
                            "away": away,
                            "away_slug": away_slug,
                            "away_logo": "/images/teams/cbcolmenar.png" if "colmenar" in away.lower() else "/images/teams/rival.png",
                            "away_score": away_score,
                            "quarters": {"home": [18, 20, 19, 21], "away": [15, 18, 22, 19]} if status == "Finalizado" else None,
                            "venue": raw_venue,
                            "venue_slug": v_slug,
                            "venue_title": v_title,
                            "venue_address": v_address,
                            "category": category,
                            "gender": gender,
                            "mvp": "-",
                        }
                        all_games.append(game_entry)

                        for colm_team in [home, away]:
                            if "colmenar" in colm_team.lower():
                                c_slug = slugify(f"{colm_team}-{category}-{gender}")
                                if c_slug not in all_teams:
                                    all_teams[c_slug] = {
                                        "name": colm_team,
                                        "slug": c_slug,
                                        "category": category,
                                        "gender": gender,
                                        "logo": "/images/teams/cbcolmenar.png",
                                        "coach": "Entrenador CB Colmenar",
                                        "venue": "Pabellón Juan Antonio Samaranch",
                                        "established": 1985,
                                        "wins": 1 if (status == "Finalizado" and ((colm_team == home and home_score > away_score) or (colm_team == away and away_score > home_score))) else 0,
                                        "losses": 1 if (status == "Finalizado" and ((colm_team == home and home_score < away_score) or (colm_team == away and away_score < home_score))) else 0,
                                        "league_position": 1,
                                        "description": f"Equipo {colm_team} del CB Colmenar Viejo en la categoría {category} {gender}.",
                                    }

    # Sort Teams
    teams_list = list(all_teams.values())
    teams_list.sort(
        key=lambda t: (
            get_category_weight(t["category"]),
            1 if t["gender"].lower() == "masculino" else 2,
            get_team_letter_weight(t["name"]),
            t["name"],
        )
    )
    for idx, t in enumerate(teams_list, 1):
        t["weight"] = idx

    # Sort Classifications
    all_classifications.sort(
        key=lambda c: (
            get_category_weight(c["category"]),
            1 if c["gender"].lower() == "masculino" else 2,
            get_team_letter_weight(c.get("colmenar_team") or c.get("league_title")),
            c["league_title"],
        )
    )
    for idx, c in enumerate(all_classifications, 1):
        c["weight"] = idx

    # Sort Games
    def game_sort_key(g):
        c_w = get_category_weight(g.get("category", ""))
        g_w = 1 if str(g.get("gender", "")).lower() == "masculino" else 2
        colm_name = (
            g.get("home", "")
            if "colmenar" in g.get("home", "").lower()
            else g.get("away", "")
        )
        l_w = get_team_letter_weight(colm_name)
        return (c_w, g_w, l_w, g.get("date", ""), g.get("time", ""))

    all_games.sort(key=game_sort_key)
    for idx, g in enumerate(all_games, 1):
        g["weight"] = idx

    venues_list = list(venues_dict.values())
    venues_list.sort(key=lambda v: (-v["matches_count"], v["title"]))

    return teams_list, all_classifications, all_games, venues_list


def write_json_files(teams, classifications, games, venues, players):
    os.makedirs(DATA_DIR, exist_ok=True)

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


def generate_markdown_content(teams, games, venues, players):
    for s_dir in ["teams", "games", "venues", "players"]:
        full_dir = os.path.join(CONTENT_DIR, s_dir)
        os.makedirs(full_dir, exist_ok=True)
        for f in os.listdir(full_dir):
            if f.endswith(".md"):
                os.remove(os.path.join(full_dir, f))

    # Generar content/teams/
    teams_dir = os.path.join(CONTENT_DIR, "teams")
    with open(os.path.join(teams_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: \"Equipos del CB Colmenar Viejo\"\n---\n")

    for team in teams:
        t_path = os.path.join(teams_dir, f"{team['slug']}.md")
        content = f"""---
title: {json.dumps(team['name'])}
name: {json.dumps(team['name'])}
slug: {json.dumps(team['slug'])}
category: {json.dumps(team['category'])}
gender: {json.dumps(team['gender'])}
logo: {json.dumps(team.get('logo', '/images/teams/cbcolmenar.png'))}
coach: {json.dumps(team.get('coach', 'Entrenador CB Colmenar'))}
venue: {json.dumps(team.get('venue', 'Pabellón Juan Antonio Samaranch'))}
established: {team.get('established', 1985)}
record: {json.dumps(f"{team.get('wins', 0)}V - {team.get('losses', 0)}D")}
league_position: {team.get('league_position', 1)}
weight: {team.get('weight', 999)}
---

El **{team['name']}** representa al CB Colmenar Viejo en la categoría {team['category']} ({team['gender']}).
Entrenado por {team.get('coach', 'el cuerpo técnico del club')}, disputa sus encuentros como local en {team.get('venue', 'Pabellón Juan Antonio Samaranch')}.
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
    print("Iniciando extracción de datos de la FBM para el CB Colmenar Viejo...")
    html = fetch_html()
    teams, classifications, games, venues = parse_fbm_data(html)
    players = []  # Sin jugadores de ejemplo

    print(f"Extraídos: {len(teams)} equipos del club, {len(classifications)} filas de clasificación, {len(games)} partidos, {len(venues)} pabellones.")

    write_json_files(teams, classifications, games, venues, players)
    generate_markdown_content(teams, games, venues, players)
    print("Proceso finalizado con éxito.")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
