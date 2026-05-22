#!/usr/bin/env python3
"""
Asterism sync pipeline: fetch, construct, and write one constellation.
Usage:
  python3 scripts/sync-asterisms.py ORION
  python3 scripts/sync-asterisms.py --all           # rebuild all constellations
  python3 scripts/sync-asterisms.py --list          # list known constellations
"""
import json, re, os, sys, urllib.request
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "assets", "json")
SHARED_JS = os.path.join(ROOT, "assets", "js", "backgrounds", "shared.js")
STEL_URL = ("https://api.github.com/repos/Stellarium/stellarium/"
            "contents/skycultures/modern/index.json")
STEL_CACHE = os.path.join(JSON_DIR, "stellarium_index.json")
MAG_CUT = 5.5

# ── Known main star HIPs and connections ───────────────
# Canonical asterism connections verified against Stellarium's IAU stick figures.
# For new constellations, add an entry here.
KNOWN = {
    "ORION": {
        "name": "Orion", "tag": "always: true",
        "main": [("Bellatrix", 25336), ("Betelgeuse", 27989), ("Alnitak A", 26727),
                 ("Alnilam", 26311), ("Mintaka AB", 25930), ("Saiph", 27366), ("Rigel", 24436)],
        "conns": [[0,1],[2,3],[3,4],[0,3],[1,2],[2,5],[4,6],[5,6]],
    },
    "CASSIOPEIA": {
        "name": "Cassiopeia", "tag": "always: true",
        "main": [("Caph", 6686), ("Schedar", 8886), ("Tiansi", 3179),
                 ("Ruchbah", 4427), ("Segin", 746)],
        "conns": [[0,1],[1,2],[2,3],[3,4]],
    },
    "LYRA": {
        "name": "Lyra", "tag": 'date: "27/07"',
        "main": [("Vega", 91262), ("Sheliak", 91971), ("Sulafat", 92420)],
        "conns": [[0,2],[2,1],[1,0]],
    },
    "CYGNUS": {
        "name": "Cygnus", "tag": 'date: "12/08"',
        "main": [("Deneb", 102098), ("Sadr", 100453), ("Albireo", 102488),
                 ("Fawaris", 94779), ("Aljanah", 95853)],
        "conns": [[0,1],[1,2],[3,1],[1,4]],
    },
    "GEMINI": {
        "name": "Gemini", "tag": 'date: "04/09"',
        "main": [("Castor A", 36850), ("Pollux", 37826), ("Alhena", 32362),
                 ("Wasat", 36962), ("Mebsuta", 35550)],
        "conns": [[0,1],[1,4],[0,3],[3,1],[4,3]],
    },
    "SCORPIUS": {
        "name": "Scorpius", "tag": 'date: "26/10"',
        "main": [("Dschubba", 78401), ("Acrab", 78820), ("Antares", 80763),
                 ("Wei", 78265), ("Lesath", 85696), ("Shaula", 85927),
                 ("Sargas", 86228), ("Girtab", 86670)],
        "conns": [[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7]],
    },
    "ANDROMEDA": {
        "name": "Andromeda", "tag": 'date: "31/03"',
        "main": [("Alpheratz", 677), ("Mirach", 3092), ("Almach", 5447),
                 ("\u03b4 And", 9640), ("51 And", 4436), ("Udkadua", 3881)],
        "conns": [[0,1],[1,2],[2,4],[2,3],[3,5]],
    },
}

CONS_ID = {v["name"]: k for k, v in KNOWN.items()}

# ── Fetchers ───────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")

def fetch_stellarium():
    if os.path.exists(STEL_CACHE):
        print(f"  Using cached {STEL_CACHE}")
        with open(STEL_CACHE) as f:
            return json.load(f)
    print("  Fetching Stellarium index.json...")
    data = json.loads(fetch(STEL_URL))
    if data.get("encoding") == "base64":
        import base64
        data = json.loads(base64.b64decode(data["content"]))
    os.makedirs(JSON_DIR, exist_ok=True)
    with open(STEL_CACHE, "w") as f:
        json.dump(data, f, indent=2)
    return data

def fetch_wikipedia(constellation):
    """Fetch and parse Wikipedia star table for a constellation."""
    page = f"List_of_stars_in_{constellation}"
    print(f"  Fetching Wikipedia: {page}...")
    html = fetch(f"https://en.wikipedia.org/w/index.php?title={page}&printable=yes")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    header = False
    cols = {}
    stars = []
    for row_html in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL)
        texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        # Column detection by keywords in header text
        if "HIP" in texts and not header:
            header = True
            for i, t in enumerate(texts):
                lower = t.lower()
                if t == "Name": cols["name"] = i
                elif t == "B" and "Bayer" not in locals(): cols["bayer"] = i
                elif "hip" in lower: cols["hip"] = i
                elif lower == "ra": cols["ra"] = i
                elif lower == "dec": cols["dec"] = i
                elif "vis" in lower or "mag" in lower:
                    if "mag" not in cols: cols["mag"] = i
                elif "sp" in lower: cols["spec"] = i
                elif "notes" in lower: cols["notes"] = i
            continue
        if not header:
            continue
        hip = None
        if "hip" in cols and cols["hip"] < len(texts):
            m = re.search(r"(\d+)", texts[cols["hip"]])
            if m: hip = int(m.group(1))
        if hip is None:
            continue
        star = {"hip": hip}
        # Name from the Name column
        if "name" in cols and cols["name"] < len(cells):
            raw_name = re.sub(r'<[^>]+>', '', cells[cols["name"]]).strip()
            if raw_name:
                star["name"] = raw_name
        # Bayer letter
        if "bayer" in cols and cols["bayer"] < len(texts):
            star["bayer_letter"] = texts[cols["bayer"]]
        # Magnitude
        if "mag" in cols and cols["mag"] < len(texts):
            try: star["mag"] = float(texts[cols["mag"]])
            except ValueError: pass
        # Spectral type
        if "spec" in cols and cols["spec"] < len(texts):
            raw = texts[cols["spec"]]
            m = re.search(r'([OBAFGKMLT]\d+(?:\.\d+)?(?:[IV]+(?:\s?[ab])?)?)', raw)
            if m: star["spec"] = m.group(1)
        # RA/Dec
        if "ra" in cols and cols["ra"] < len(cells):
            raw = re.sub(r'<[^>]+>', '', cells[cols["ra"]]).strip()
            parts = re.findall(r"(\d+)[h\s:]+(\d+)[m\s:]*(\d+(?:\.\d+)?)", raw)
            if parts: star["ra"] = [float(x) for x in parts[0]]
        if "dec" in cols and cols["dec"] < len(cells):
            raw = re.sub(r'<[^>]+>', '', cells[cols["dec"]]).strip()
            parts = re.findall(r"([+-]?\d+)[°\s]+(\d+)[′\s]*(\d+(?:\.\d+)?)", raw)
            if parts: star["dec"] = [float(x) for x in parts[0]]
        stars.append(star)
    print(f"  Parsed {len(stars)} stars")
    return stars

# ── Star Naming ────────────────────────────────────────
def star_name(wiki_entry):
    """Determine the best name for a star entry from Wikipedia data."""
    if "name" in wiki_entry:
        n = wiki_entry["name"]
        if n and len(n) < 40:
            return n
    return str(wiki_entry.get("hip", ""))

# ── Generate consData JS ───────────────────────────────
def ra_order(s):
    if isinstance(s.get("ra"), (list, tuple)) and len(s["ra"]) >= 2:
        return float(s["ra"][0]) + float(s["ra"][1]) / 60.0
    return 0.0

def to_js(val):
    if val is None: return "null"
    return json.dumps(val)

def fmt_arr(v, default="0"):
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return f"[{v[0]}, {v[1]}, {v[2]}]"
    return f"[{default}, {default}, {default}]"

def build_consdata_entry(cons_key):
    """Build a consData JS entry string from KNOWN config + Wikipedia data."""
    cfg = KNOWN[cons_key]
    wiki_stars = fetch_wikipedia(cfg["name"])

    # Step 1: build name-HIP mapping from known main stars
    main_hips = {hip: name for name, hip in cfg["main"]}
    hip_bayer = {s["hip"]: star_name(s) for s in wiki_stars if star_name(s)}

    # Step 2: collect all bright stars from Wikipedia (mag <= MAG_CUT)
    all_bright = []
    seen_hips = set()
    for ws in wiki_stars:
        if "mag" in ws and ws["mag"] <= MAG_CUT and ws["hip"] not in seen_hips:
            seen_hips.add(ws["hip"])
            name = main_hips.get(ws["hip"], hip_bayer.get(ws["hip"], str(ws["hip"])))
            all_bright.append({
                "name": name,
                "hip": ws["hip"],
                "ra": ws.get("ra", [0,0,0]),
                "dec": ws.get("dec", [0,0,0]),
                "mag": ws["mag"],
                "spec": ws.get("spec"),
            })

    # Step 3: main stars in canonical order (config order, not RA-sorted)
    main_names = [p[0] for p in cfg["main"]]
    name_map = {s["name"]: s for s in all_bright if s["name"] in main_names}

    ordered = []
    for n in main_names:
        if n in name_map:
            ordered.append(name_map[n])

    remaining = sorted([s for s in all_bright if s["name"] not in main_names], key=lambda s: s["mag"])
    ordered.extend(remaining)

    # Step 4: build connections using bright_mag sorted array for cross-ref
    bright_mag = sorted(all_bright, key=lambda s: s["mag"])
    bm_names = {i: s["name"] for i, s in enumerate(bright_mag)}

# Map canonical connections (by main list position) to bright_mag indices
    main_to_bm = {}
    for i, name in enumerate(main_names):
        for j, s in enumerate(bright_mag):
            if s["name"] == name:
                main_to_bm[i] = j
                break

    ast_conns = []
    for c in cfg["conns"]:
        i1 = main_to_bm.get(c[0])
        i2 = main_to_bm.get(c[1])
        if i1 is not None and i2 is not None:
            ast_conns.append([i1, i2])

    # Map back to ordered array indices
    ordered_name_idx = {s["name"]: i for i, s in enumerate(ordered)}
    conns = []
    for c in ast_conns:
        n1 = bm_names.get(c[0])
        n2 = bm_names.get(c[1])
        if n1 in ordered_name_idx and n2 in ordered_name_idx:
            conns.append([ordered_name_idx[n1], ordered_name_idx[n2]])

    # Step 5: generate JS lines
    lines = []
    lines.append(f'  {{ /* {cons_key} */')
    lines.append(f'    name: "{cfg["name"]}", {cfg["tag"]},')
    lines.append(f'    stars: [')
    for s in ordered:
        ra = fmt_arr(s.get("ra"))
        dec = fmt_arr(s.get("dec"))
        spec = to_js(s.get("spec"))
        lines.append(f'      {{ name:{to_js(s["name"])}, ra:{ra}, dec:{dec}, mag:{s["mag"]:.2f}, spec:{spec} }},')
    lines.append(f'    ],')
    lines.append(f'    connections: {json.dumps(conns)},')
    lines.append(f'    mainIndices: {json.dumps(list(range(len(cfg["main"]))))},')
    lines.append(f'  }},')
    return "\n".join(lines), ordered

# ── Update shared.js ──────────────────────────────────
def update_shared(cons_key, entry_js):
    with open(SHARED_JS) as f:
        content = f.read()

    # Find the constellation block
    pattern = r'{ /\* ' + cons_key + r' \*/(.*?)\n  },'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print(f"  Replacing existing entry for {cons_key}")
        content = content[:match.start()] + entry_js + content[match.end():]
    else:
        # Insert before the closing ];
        content = content.replace("];", entry_js + "\n];")

    with open(SHARED_JS, "w") as f:
        f.write(content)
    print(f"  Updated {SHARED_JS}")

# ── Main ───────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list" in args:
        print("Known constellations:")
        for k, v in KNOWN.items():
            print(f"  {k:15s} ({v['name']})")
        sys.exit(0)

    if "--all" in args:
        targets = list(KNOWN.keys())
    else:
        targets = [a.upper() for a in args if a.upper() in KNOWN]
        if not targets:
            print(f"Usage: {sys.argv[0]} ORION")
            print(f"       {sys.argv[0]} --all")
            print(f"       {sys.argv[0]} --list")
            print(f"Known: {', '.join(KNOWN.keys())}")
            sys.exit(1)

    fetch_stellarium()

    for cons_key in targets:
        print(f"\n=== {cons_key} ===")
        entry_js, stars = build_consdata_entry(cons_key)
        update_shared(cons_key, entry_js)
        print(f"  Main stars: {[s['name'] for s in stars if s['name'] in [p[0] for p in KNOWN[cons_key]['main']]]}")

    print("\nDone.")