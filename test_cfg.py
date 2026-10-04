import json, re

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

with open("data/club.json", "r") as f:
    cfg = json.load(f)

cfg["venue_slug"] = slugify(cfg["venue_address"])

with open("data/club.json", "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
