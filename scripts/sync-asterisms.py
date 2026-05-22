#!/usr/bin/env python3
"""
Asterism sync pipeline: fetch, construct, and write one constellation.
Usage:
  python3 scripts/sync-asterisms.py Orion
  python3 scripts/sync-asterisms.py --all         # rebuild all known
  python3 scripts/sync-asterisms.py --list        # list IAU constellations
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

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")

def fetch_stellarium():
    if os.path.exists(STEL_CACHE):
        print(f"  Using cached {STEL_CACHE}")
        with open(STEL_CACHE) as f: return json.load(f)
    print("  Fetching Stellarium index.json...")
    data = json.loads(fetch(STEL_URL))
    if data.get("encoding") == "base64":
        import base64; data = json.loads(base64.b64decode(data["content"]))
    os.makedirs(JSON_DIR, exist_ok=True)
    with open(STEL_CACHE, "w") as f: json.dump(data, f, indent=2)
    return data

def fetch_wikipedia(constellation):
    page = f"List_of_stars_in_{constellation}"
    print(f"  Fetching Wikipedia: {page}...")
    html = fetch(f"https://en.wikipedia.org/w/index.php?title={page}&printable=yes")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    header = False; cols = {}; stars = []
    for raw in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', raw, re.DOTALL)
        texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if "HIP" in texts and not header:
            header = True
            for i, t in enumerate(texts):
                l = t.lower()
                if t == "Name": cols["name"] = i
                elif "hip" in l: cols["hip"] = i
                elif l == "ra": cols["ra"] = i
                elif l == "dec": cols["dec"] = i
                elif "vis" in l or "mag" in l:
                    if "mag" not in cols: cols["mag"] = i
                elif "sp" in l: cols["spec"] = i
                elif "notes" in l or "note" in l: cols["notes"] = i
            continue
        if not header: continue
        hip = None
        if "hip" in cols and cols["hip"] < len(texts):
            m = re.search(r"(\d+)", texts[cols["hip"]])
            hip = int(m.group(1)) if m else None
        if hip is None: continue
        star = {"hip": hip}
        # Name from Name column
        if "name" in cols and cols["name"] < len(cells):
            raw = re.sub(r'<[^>]+>', '', cells[cols["name"]]).strip()
            if raw: star["name"] = raw
        # Common name from Notes column (if it looks like a proper name)
        if "notes" in cols and cols["notes"] < len(cells):
            notes_raw = cells[cols["notes"]]
            # Common name is often the initial text before any tags/semicolons
            # Strip tags and take the first semicolon-delimited part
            text = re.sub(r'<sup[^>]*>.*?</sup>', ' ', notes_raw).strip()
            text = re.sub(r'<[^>]+>', ' ', text).strip()
            text = unescape(text)
            # Split by ; or , and take the first meaningful part
            chunks = re.split(r'[;,]\s*', text)
            potential = chunks[0].strip() if chunks else ""
            # Filter out junk
            if potential and len(potential) > 1 and not potential.startswith("[") and not potential.startswith("&"):
                # Clean up any trailing brackets
                potential = re.sub(r'\s*\[.*?\]', '', potential).strip()
                if not re.search(r'(star|variable|binary|spectroscopic|brightest|planet|cluster|nebula|NGC|HD|HIP|max|min|ΔV|P\s*=)', potential, re.I):
                    star["notes_name"] = potential
        if "mag" in cols and cols["mag"] < len(texts):
            try: star["mag"] = float(texts[cols["mag"]])
            except: pass
        if "spec" in cols and cols["spec"] < len(texts):
            m = re.search(r'([OBAFGKMLT]\d+(?:\.\d+)?(?:[IV]+(?:\s?[ab])?)?)', texts[cols["spec"]])
            if m: star["spec"] = m.group(1)
        if "ra" in cols and cols["ra"] < len(cells):
            raw = unescape(re.sub(r'<[^>]+>', '', cells[cols["ra"]])).strip()
            parts = re.findall(r"(\d+)[h\s:]+(\d+)[m\s:]*(\d+(?:\.\d+)?)", raw)
            if parts: star["ra"] = [float(x) for x in parts[0]]
        if "dec" in cols and cols["dec"] < len(cells):
            raw = unescape(re.sub(r'<[^>]+>', '', cells[cols["dec"]])).strip().replace("\u2212", "-")
            parts = re.findall(r"([+-]?\d+)[°\s]+(\d+)[′\s]*(\d+(?:\.\d+)?)", raw)
            if parts: star["dec"] = [float(x) for x in parts[0]]
        stars.append(star)
    print(f"  Parsed {len(stars)} stars"); return stars

def star_name(s):
    """Best name: prefer Notes column common name if Name column is a Bayer letter."""
    n = (s.get("name") or "").strip()
    nn = s.get("notes_name", "")
    if not n:
        return nn if nn else str(s.get("hip", ""))
    # If Name is a Bayer designation (Greek letter + constellation), prefer Notes
    if re.search(r'^[α-ωΑ-Ω]', n):
        return nn if nn else n
    # Also handle spelled-out Greek letters
    greek_words = ['Alpha','Beta','Gamma','Delta','Epsilon','Zeta','Eta','Theta',
                   'Iota','Kappa','Lambda','Mu','Nu','Xi','Omicron','Pi','Rho',
                   'Sigma','Tau','Upsilon','Phi','Chi','Psi','Omega']
    parts = n.split()
    if parts and parts[0] in greek_words:
        return nn if nn else n
    return n

def find_cons(stel, name):
    name_l = name.lower()
    for cons in stel.get("constellations", []):
        cn = cons.get("common_name", {})
        if cn.get("english", "").lower() == name_l or \
           cn.get("native", "").lower() == name_l:
            return cons
    return None

def best_month(ra_hours):
    sun_ra = (ra_hours + 12) % 24; m = int((sun_ra - 6) / 2) + 1
    return max(1, min(12, m))

def fmt_pos(v):
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return f"[{v[0]}, {v[1]}, {v[2]}]"
    return "[0, 0, 0]"

def build_entry(name):
    stel = fetch_stellarium(); wiki = fetch_wikipedia(name)
    sc = find_cons(stel, name)
    if not sc: print(f"  ERROR: '{name}' not found in Stellarium"); return None, []
    lines = sc.get("lines", []); print(f"  Stellarium lines: {len(lines)}")

    # Deduplicate Wikipedia stars by HIP (keep brightest)
    hip_stars = {}
    for ws in wiki:
        h = ws["hip"]
        if h not in hip_stars or ws.get("mag", 99) < hip_stars[h].get("mag", 99):
            hip_stars[h] = ws

    # Resolve names: use best name from Wikipedia data
    for s in hip_stars.values():
        s["best_name"] = star_name(s)

    # Collect HIPs from Stellarium lines
    line_hips = set()
    for ln in lines:
        for h in ln:
            if isinstance(h, int): line_hips.add(h)

    # Bright stars that are in both Stellarium and Wikipedia
    bright_line = {}
    for h in line_hips:
        ws = hip_stars.get(h)
        if ws and "mag" in ws and ws["mag"] <= MAG_CUT:
            bright_line[h] = ws

    if not bright_line:
        print("  ERROR: no bright stars matched between Wikipedia and Stellarium")
        return None, []

    # Determine main asterism: merge ALL Stellarium lines, filter to bright stars.
    MAIN_MAG_CUT = 4.5
    # Collect all unique HIPs used in any Stellarium line, with mag filter
    line_hip_set = set()
    for ln in lines:
        for h in ln:
            if isinstance(h, int) and h in bright_line and bright_line[h].get("mag", 99) <= MAIN_MAG_CUT:
                line_hip_set.add(h)

    # Build all connections from consecutive filtered stars in each line
    raw_pair_set = set()
    for ln in lines:
        flt = [h for h in ln if isinstance(h, int) and h in line_hip_set]
        for i in range(len(flt) - 1):
            raw_pair_set.add((flt[i], flt[i+1]))

    # Build a graph: follow the chain of connections
    graph = {}
    for a, b in raw_pair_set:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)

    # Find the main chain: start from a star with degree 1, follow the path
    degree1 = [h for h in line_hip_set if len(graph.get(h, [])) == 1]
    # Also include stars with degree > 1 (junctions in the chain)
    main_hips = list(line_hip_set)

    # Post-process: insert missing bright stars that are between consecutive
    # main stars in RA. This handles cases like Lesath in Scorpius that are
    # part of the traditional asterism but not in the IAU stick figure.
    def ra_of(hip):
        ws = bright_line.get(hip) or hip_stars.get(hip)
        if ws: r = ws.get("ra", [0, 0, 0])
        else: r = [0, 0, 0]
        return r[0] + r[1] / 60.0 if len(r) >= 2 else 0

    sorted_hips = sorted(line_hip_set, key=ra_of)
    inserted = set()
    # Rare cases: bright stars that are part of the canonical asterism but not in
    # the IAU stick figure (e.g. Lesath = HIP 85696 in Scorpius).
    MISSING_BRIDGES = {
        85696: {"after": 84143},  # Lesath, insert after η Sco (HIP 84143) in Scorpius
    }
    for h, hint in MISSING_BRIDGES.items():
        ws = hip_stars.get(h)
        if ws and "mag" in ws and ws["mag"] <= MAIN_MAG_CUT and h not in line_hip_set:
            after = hint.get("after")
            if after and after in sorted_hips:
                idx = sorted_hips.index(after)
                if idx + 1 < len(sorted_hips) and sorted_hips[idx + 1] != h:
                    inserted.add(h)
                    sorted_hips.insert(idx + 1, h)

    main_hips = sorted_hips

    # Build full ordered list
    all_hips = main_hips.copy()
    rest_line = sorted([h for h in bright_line if h not in main_hips],
                       key=lambda h: bright_line[h].get("mag", 99))
    all_hips.extend(rest_line)
    rest = sorted([h for h in hip_stars if h not in all_hips and "mag" in hip_stars[h] and hip_stars[h]["mag"] <= MAG_CUT],
                  key=lambda h: hip_stars[h]["mag"])
    all_hips.extend(rest)

    ordered = [hip_stars[h] for h in all_hips if h in hip_stars]
    oidx = {s["best_name"]: i for i, s in enumerate(ordered)}

    # Build connections from the merged pair set
    conns = []
    for a, b in raw_pair_set:
        if a in main_hips and b in main_hips:
            wa, wb = hip_stars.get(a), hip_stars.get(b)
            if wa and wb:
                n1, n2 = wa["best_name"], wb["best_name"]
                if n1 in oidx and n2 in oidx:
                    conns.append([oidx[n1], oidx[n2]])

    # Also add connections for inserted stars (bridge between their neighbors)
    for h in inserted:
        r = ra_of(h)
        # Find neighbors in main_hips
        for i in range(len(main_hips) - 1):
            if main_hips[i + 1] == h:
                # h was inserted after position i, so connect previous -> h -> next
                prev_h = main_hips[i]
                next_h = main_hips[i + 2] if i + 2 < len(main_hips) else None
                for partner in [prev_h, next_h]:
                    if partner:
                        wa, wb = hip_stars.get(h), hip_stars.get(partner)
                        if wa and wb:
                            n1, n2 = wa["best_name"], wb["best_name"]
                            if n1 in oidx and n2 in oidx:
                                conns.append([oidx[n1], oidx[n2]])

    # Known visibility tags: `always: true` for circumpolar/always-visible
    # constellations; specific date for the rest (peak midnight transit).
    main_names = [hip_stars[h]["best_name"] for h in main_hips]
    SPECIAL_TAGS = {
        "Orion": "always: true",
        "Cassiopeia": "always: true",
        "Lyra": 'date: "27/07"',
        "Cygnus": 'date: "12/08"',
        "Gemini": 'date: "04/09"',
        "Scorpius": 'date: "26/10"',
        "Andromeda": 'date: "31/03"',
    }
    tag = SPECIAL_TAGS.get(name, "always: true")

    ck = name.upper().replace(" ", "_")
    js = [
        f'  {{ /* {ck} */',
        f'    name: "{name}", {tag},',
        f'    stars: [',
    ]
    for s in ordered:
        ra = fmt_pos(s.get("ra")); dec = fmt_pos(s.get("dec"))
        spec = json.dumps(s["spec"]) if s.get("spec") else "null"
        nm = s["best_name"]
        js.append(f'      {{ name:{json.dumps(nm)}, ra:{ra}, dec:{dec}, mag:{s["mag"]:.2f}, spec:{spec} }},')
    js.append(f'    ],')
    js.append(f'    connections: {json.dumps(conns)},')
    js.append(f'    mainIndices: {json.dumps(list(range(len(main_hips))))},')
    js.append(f'  }},')
    print(f"  Main stars: {main_names}")
    return "\n".join(js), ordered

def update_shared(ck, entry):
    with open(SHARED_JS) as f: c = f.read()
    # Match with any leading whitespace on both start and end
    p = r'^\s*\{ /\* ' + ck + r' \*/(.*?)\n\s*\},'
    m = re.search(p, c, re.DOTALL | re.MULTILINE)
    if m:
        c = c[:m.start()] + entry.strip() + "\n" + c[m.end():]
    else:
        c = c.replace("];", entry.strip() + "\n];")
    with open(SHARED_JS, "w") as f: f.write(c)
    print(f"  Updated {SHARED_JS}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--list" in args:
        for cons in sorted(fetch_stellarium().get("constellations", []), key=lambda x: x.get("common_name", {}).get("english", "")):
            cn = cons.get("common_name", {}); eng = cn.get("english", "")
            nat = cn.get("native", "")
            if eng or nat: print(f"  {eng or nat}")
        sys.exit(0)
    if "--all" in args:
        # Pre-built list: constellations that have been verified
        targets = ["Orion", "Cassiopeia", "Lyra", "Cygnus", "Gemini", "Scorpius", "Andromeda"]
    else:
        targets = [" ".join(a.capitalize() for a in arg.split()) for arg in args]
        targets = [t for t in targets if t]
    if not targets:
        print(f"Usage: {sys.argv[0]} Orion\n       {sys.argv[0]} --all\n       {sys.argv[0]} --list")
        sys.exit(1)
    for name in sorted(targets):
        print(f"\n=== {name.upper()} ===")
        entry_js, _ = build_entry(name)
        if entry_js: update_shared(name.upper().replace(" ", "_"), entry_js)
    print("\nDone.")
