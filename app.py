from flask import Flask, render_template, request
import json
from flask import jsonify

app = Flask(__name__)

# Debug flag: enable temporary logging for matching issues
DEBUG_MATCH = True

# Load language-specific text files
try:
    with open("data/crops_en.json", "r", encoding="utf-8") as f:
        texts_en = json.load(f)
except Exception:
    texts_en = []

try:
    with open("data/crops_te.json", "r", encoding="utf-8") as f:
        texts_te = json.load(f)
except Exception:
    texts_te = []

# Build separate master crop lists for English and Telugu
# This reduces ambiguity when matching user input in different languages.
# crops_master_en: primary records derived from English file
# crops_master_te: primary records derived from Telugu file
texts_en_map = {t.get('name'): t for t in texts_en}
texts_te_map = {t.get('name'): t for t in texts_te}

# Also index by image for reliable cross-language lookups
texts_en_by_image = {t.get('image'): t for t in texts_en}
texts_te_by_image = {t.get('image'): t for t in texts_te}

crops_master_en = []
en_to_te = {t.get('name'): t for t in texts_te}
for t in texts_en:
    name = t.get('name')
    te = en_to_te.get(name, {})
    crops_master_en.append({
        'name_en': name,
        'name_te': te.get('name'),
        'image': t.get('image'),
        'season': t.get('season'),
        'soil': (t.get('soil') or '').lower(),
        'water': t.get('water')
    })

# Build Telugu-primary master (fall back to English fields when available)
crops_master_te = []
te_to_en = {t.get('name'): t for t in texts_en}
for t in texts_te:
    name_te = t.get('name')
    en = te_to_en.get(name_te, {})
    crops_master_te.append({
        'name_en': en.get('name') or t.get('name_en'),
        'name_te': name_te,
        'image': t.get('image') or en.get('image'),
        'season': t.get('season') or en.get('season'),
        'soil': (t.get('soil') or en.get('soil') or '').lower(),
        'water': t.get('water') or en.get('water')
    })

# For endpoints that rely on canonical season/soil keys, use the English master
combined_master = crops_master_en

# quick maps already set above (texts_en_map, texts_te_map)

def combine_display(master):
    """Create a display dict with both _en and _te fields for templates."""
    name_en = master.get('name_en') or master.get('name')
    image = master.get('image')
    # find english/te entries by English name first, then fall back to image-based lookup
    en = texts_en_map.get(name_en, {})
    if not en and image:
        en = texts_en_by_image.get(image, {})
    te = texts_te_map.get(name_en, {})
    if not te and image:
        te = texts_te_by_image.get(image, {})

    return {
        'name_en': en.get('name') or master.get('name_en') or '',
        'name_te': te.get('name') or master.get('name_te') or '',
        'image': master.get('image'),
        'season': master.get('season'),
        'soil': master.get('soil'),
        'water': master.get('water'),
        'fertilizer_en': en.get('fertilizer') or master.get('fertilizer_en') or '',
        'fertilizer_te': te.get('fertilizer') or master.get('fertilizer_te') or '',
        'explanation_en': en.get('explanation') or master.get('explanation_en') or '',
        'explanation_te': te.get('explanation') or master.get('explanation_te') or '',
        'land_preparation_en': en.get('land_preparation') or master.get('land_preparation_en') or '',
        'land_preparation_te': te.get('land_preparation') or master.get('land_preparation_te') or '',
        'seed_info_en': en.get('seed_info') or master.get('seed_info_en') or '',
        'seed_info_te': te.get('seed_info') or master.get('seed_info_te') or '',
        'climate_en': en.get('climate') or master.get('climate_en') or '',
        'climate_te': te.get('climate') or master.get('climate_te') or '',
        'soil_type_en': en.get('soil_type') or master.get('soil_type_en') or '',
        'soil_type_te': te.get('soil_type') or master.get('soil_type_te') or '',
    }


# ----- Matching / scoring helpers -----
def _norm_text(s: str) -> str:
    if not s:
        return ''
    try:
        return ''.join(ch for ch in s.lower().strip())
    except Exception:
        return s.lower().strip()


def _levenshtein(a: str, b: str) -> int:
    a = a or ''
    b = b or ''
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def _score_record(rec: dict, user_crop: str = '', user_season: str = '', user_soil: str = '', user_image: str = '') -> int:
    """Compute a heuristic score for how well `rec` matches the provided user hints.

    We give large weight to image and exact name matches, medium weight to
    season/soil equality, and small fuzzy-match weight for similar names.
    """
    score = 0
    uname = (user_crop or '').strip().lower()
    uimg = (user_image or '').strip().lower()
    useason = (user_season or '').strip().lower()
    usoil = (user_soil or '').strip().lower()

    # image strong match
    if uimg and rec.get('image') and uimg == (rec.get('image') or '').strip().lower():
        score += 1000

    # exact name matches (en / te)
    name_en = (rec.get('name_en') or '').strip().lower()
    name_te = (rec.get('name_te') or '').strip().lower()
    if uname:
        if uname == name_en or uname == name_te:
            score += 500
        elif name_en and uname in name_en:
            score += 200
        elif name_te and uname in name_te:
            score += 200
        else:
            # fuzzy distance
            # smaller distance -> higher score
            target = name_en or name_te or ''
            if target:
                d = _levenshtein(uname, target)
                # allow some tolerance; score decays with distance
                score += max(0, 120 - (d * 10))

    # season match
    if useason:
        norm_rec_season = _norm_season_value(rec.get('season') or '')
        if useason == norm_rec_season or useason in [norm_rec_season, rec.get('season') or '']:
            score += 200

    # soil match (compare normalized keys)
    if usoil:
        rec_soil = (rec.get('soil') or '').strip().lower()
        if usoil == rec_soil or usoil in rec_soil:
            score += 150

    return int(score)


def _norm_season_value(val: str) -> str:
    """Normalize season values (Telugu or English) to canonical english keys."""
    if not val:
        return ''
    v = val.strip().lower()
    rev = {
        'ఖరీఫ్': 'kharif',
        'రబీ': 'rabi',
        'జైద్': 'zaid'
    }
    return rev.get(v, v)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/language")
def language():
    return render_template("language.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/crop_input")
def crop_input():
    return render_template("crop_input.html")

@app.route("/season_input")
def season_input():
    return render_template("season_input.html")

@app.route("/soil_input")
def soil_input():
    return render_template("soil_input.html")


# -------- CROP BASED INPUT --------
@app.route("/crop_result", methods=["POST"])
def crop_result():
    user_crop_raw = request.form.get("crop") or ""
    user_crop = user_crop_raw.strip().lower()
    user_image_raw = request.form.get("image") or ""
    user_image = user_image_raw.strip().lower()
    lang = request.form.get("language") or "en"
    if DEBUG_MATCH:
        print(f"[DEBUG] crop_result received crop={request.form.get('crop')!r} language={lang!r}")

    # Choose which master to search based on the requested language.
    # If the user asked Telugu, prefer the Telugu-primary master so matching
    # against Telugu names is more reliable. Otherwise use the English master.
    master_list = crops_master_te if lang == 'te' else crops_master_en

    # If the client supplied an image, try a direct lookup in the canonical master first.
    if user_image:
        for c in combined_master:
            if (c.get('image') or '').strip().lower() == user_image:
                if DEBUG_MATCH:
                    print(f"[DEBUG] Direct image match in combined_master: image={user_image!r} -> {c.get('name')!r}")
                # Build similar list and return immediately using the canonical record
                crop = c
                crop_season_norm = _norm_season_value(crop.get('season'))
                matched_image = (crop.get('image') or '').lower()
                matched_name_en = ((crop.get('name_en') or '')).strip().lower()

                def _match_season(c2):
                    return _norm_season_value(c2.get('season')) == crop_season_norm

                def _is_same_crop(c2):
                    img = (c2.get('image') or '').lower()
                    name_en = ((c2.get('name_en') or '')).strip().lower()
                    if img and matched_image and img == matched_image:
                        return True
                    if name_en and matched_name_en and name_en == matched_name_en:
                        return True
                    return False

                similar_master = [c2 for c2 in combined_master if _match_season(c2) and not _is_same_crop(c2)][:4]
                best = combine_display(crop)
                others = [combine_display(c2) for c2 in similar_master]
                return render_template("result.html", best=best, others=others, lang=lang, recommendation_type="season")
    # Use scoring against the language-preferred master to pick the best candidate
    scored = []
    for c in master_list:
        s = _score_record(c, user_crop=user_crop, user_image=user_image)
        scored.append((s, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 100:
        # threshold prevents low-quality fuzzy matches returning incorrect crops
        if DEBUG_MATCH:
            print(f"[DEBUG] No sufficient score found. Top scores: {[x[0] for x in scored][:5]}")
        return "Crop not found"

    # best candidate
    best_crop = scored[0][1]
    if DEBUG_MATCH:
        print(f"[DEBUG] Best scored crop: score={scored[0][0]} name_en={best_crop.get('name_en')!r} name_te={best_crop.get('name_te')!r}")

    crop_season_norm = _norm_season_value(best_crop.get('season'))
    matched_image = (best_crop.get('image') or '').lower()
    matched_name_en = ((best_crop.get('name_en') or '')).strip().lower()

    def _match_season(c2):
        return _norm_season_value(c2.get('season')) == crop_season_norm

    def _is_same_crop(c2):
        img = (c2.get('image') or '').lower()
        name_en = ((c2.get('name_en') or '')).strip().lower()
        if img and matched_image and img == matched_image:
            return True
        if name_en and matched_name_en and name_en == matched_name_en:
            return True
        return False

    similar_master = [c2 for c2 in combined_master if _match_season(c2) and not _is_same_crop(c2)][:4]
    best = combine_display(best_crop)
    others = [combine_display(c2) for c2 in similar_master]
    return render_template("result.html", best=best, others=others, lang=lang, recommendation_type="season")


# -------- SEASON BASED INPUT --------
@app.route("/season_result", methods=["POST"])
def season_result():
    season_input = request.form["season"].strip().lower()
    lang = request.form.get("language") or "en"

    season_map = {
        "kharif": ["kharif", "ఖరీఫ్"],
        "rabi": ["rabi", "రబీ", "రవి"],
        "zaid": ["zaid", "జైద్", "జై"]
    }

    matched_season = None
    # First try exact / substring matches
    for key, values in season_map.items():
        for v in values:
            if v and v.lower() in season_input:
                matched_season = key
                break
        if matched_season:
            break

    # If no exact/substring match, try fuzzy matching using Levenshtein distance
    if not matched_season and season_input:
        best_key = None
        best_dist = None
        # Choose candidates where distance is within a per-candidate threshold
        for key, values in season_map.items():
            for v in values:
                if not v:
                    continue
                vnorm = v.lower()
                d = _levenshtein(season_input, vnorm)
                # per-candidate threshold (allow up to ~45% of length as edits)
                allowed = max(1, int(max(len(season_input), len(vnorm)) * 0.45))
                if d <= allowed and (best_dist is None or d < best_dist):
                    best_dist = d
                    best_key = key
        if best_key is not None:
            matched_season = best_key

    matched_master = [c for c in combined_master if c.get("season") == matched_season]
    if not matched_master:
        return "No crops found for this season", 404
    # Rank season matches by score (helps when multiple crops match the same season)
    ranked = sorted([( _score_record(c, user_season=matched_season), c) for c in matched_master], key=lambda x: x[0], reverse=True)
    best_rec = ranked[0][1]
    best = combine_display(best_rec)
    others = [combine_display(c) for _, c in ranked[1:5]]
    return render_template("result.html", best=best, others=others, lang=lang, recommendation_type="season")


# -------- SOIL BASED INPUT --------
@app.route("/soil_result", methods=["POST"])
def soil_result():
    soil_input = request.form["soil"].strip().lower()
    lang = request.form["language"]

    soil_map = {
        "black": ["black", "నల్ల"],
        "red": ["red", "ఎర్ర"],
        "clayey": ["clayey", "చిక్కటి"],
        "loamy": ["loamy", "ఒండ్రు"],
        "sandy": ["sandy", "ఇసుక"]
    }

    matched_soil = None
    # Match against each soil type
    for key, values in soil_map.items():
        # Check if any soil value matches the input
        for v in values:
            if v.lower() in soil_input:
                matched_soil = key
                break
        if matched_soil:
            break

    if not matched_soil:
        return "Soil type not found", 400
    
    # Get all crops matching the soil type from master list
    matched_master = [c for c in combined_master if (c.get("soil") or "").lower() == matched_soil]

    if not matched_master:
        return f"No crops found for {matched_soil} soil", 404

    # Rank soil matches by score to pick the most relevant crop
    ranked = sorted([( _score_record(c, user_soil=matched_soil), c) for c in matched_master], key=lambda x: x[0], reverse=True)
    best_rec = ranked[0][1]
    best = combine_display(best_rec)
    others = [combine_display(c) for _, c in ranked[1:5]]

    # Return primary crop and up to 4 similar crops (soil-based)
    return render_template("result.html", best=best, others=others, lang=lang, recommendation_type="soil")


if __name__ == "__main__":
    app.run(debug=True, port=5001)


# --- API helpers for client-side mapping ---
@app.route('/api/crops')
def api_crops():
    """Return simple lists of crop names (en/te), seasons and soil keywords for client-side mapping."""
    try:
        en_names = [t.get('name') for t in texts_en if t.get('name')]
        te_names = [t.get('name') for t in texts_te if t.get('name')]
        seasons = ['kharif', 'rabi', 'zaid']
        soils = {
            'black': ['black', 'నల్ల'],
            'red': ['red', 'ఎర్ర'],
            'clayey': ['clayey', 'చిక్కటి'],
            'loamy': ['loamy', 'ఒండ్రు'],
            'sandy': ['sandy', 'ఇసుక']
        }
        return jsonify({ 'en': en_names, 'te': te_names, 'seasons': seasons, 'soils': soils })
    except Exception:
        return jsonify({ 'en': [], 'te': [], 'seasons': [], 'soils': {} })
