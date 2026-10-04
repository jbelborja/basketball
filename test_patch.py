import re
NUM_RE       = re.compile(r"^\d{1,3}$")

# simulating the row
non_empty = [
  "ARGANZUELA CENTRO BLANCO",
  "48",
  "45",
  "OROQUIETA ESPINILLO C.D.E.",
  "03/10/2026 09:15",
  "VENUE"
]

if len(non_empty) >= 5 and NUM_RE.match(non_empty[1]) and NUM_RE.match(non_empty[2]):
    home = non_empty[0]
    home_score_raw = non_empty[1]
    away_score_raw = non_empty[2]
    away = non_empty[3]
    date_time_raw = non_empty[4]
    venue = non_empty[5] if len(non_empty) > 5 else ""
    print(home, away, home_score_raw, away_score_raw)

