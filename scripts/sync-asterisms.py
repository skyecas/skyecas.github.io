#!/usr/bin/env python3
"""
Asterism sync pipeline: fetch, construct, and write one constellation.
Usage:
  python3 scripts/sync-asterisms.py Orion
  python3 scripts/sync-asterisms.py --all         # rebuild all in shared.js
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

# ── Known constellations ───────────────────────────────
KNOWN = {
    "Orion": {"tag": "always: true",
        "main": [("Bellatrix",25336),("Betelgeuse",27989),("Alnitak A",26727),
                 ("Alnilam",26311),("Mintaka AB",25930),("Saiph",27366),("Rigel",24436)],
        "conns": [[0,1],[2,3],[3,4],[0,3],[1,2],[2,5],[4,6],[5,6]]},
    "Cassiopeia": {"tag": "always: true",
        "main": [("Caph",6686),("Schedar",8886),("Tiansi",3179),("Ruchbah",4427),("Segin",746)],
        "conns": [[0,1],[1,2],[2,3],[3,4]]},
    "Lyra": {"tag": 'date: "27/07"',
        "main": [("Vega",91262),("Sheliak",91971),("Sulafat",92420)],
        "conns": [[0,2],[2,1],[1,0]]},
    "Cygnus": {"tag": 'date: "12/08"',
        "main": [("Deneb",102098),("Sadr",100453),("Albireo",102488),
                 ("Fawaris",94779),("Aljanah",95853)],
        "conns": [[0,1],[1,2],[3,1],[1,4]]},
    "Gemini": {"tag": 'date: "04/09"',
        "main": [("Castor A",36850),("Pollux",37826),("Alhena",32362),
                 ("Wasat",36962),("Mebsuta",35550)],
        "conns": [[0,1],[1,4],[0,3],[3,1],[4,3]]},
    "Scorpius": {"tag": 'date: "26/10"',
        "main": [("Dschubba",78401),("Acrab",78820),("Antares",80763),
                 ("Wei",78265),("Lesath",85696),("Shaula",85927),
                 ("Sargas",86228),("Girtab",86670)],
        "conns": [[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7]]},
    "Andromeda": {"tag": 'date: "31/03"',
        "main": [("Alpheratz",677),("Mirach",3092),("Almach",5447),
                 ("\u03b4 And",9640),("51 And",4436),("Udkadua",3881)],
        "conns": [[0,1],[1,2],[2,4],[2,3],[3,5]]},
}

# ── Fetchers ───────────────────────────────────────────
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
                if t=="Name": cols["name"]=i
                elif "hip" in l: cols["hip"]=i
                elif l=="ra": cols["ra"]=i
                elif l=="dec": cols["dec"]=i
                elif "vis" in l or "mag" in l:
                    if "mag" not in cols: cols["mag"]=i
                elif "sp" in l: cols["spec"]=i
            continue
        if not header: continue
        hip = None
        if "hip" in cols and cols["hip"]<len(texts):
            m=re.search(r"(\d+)",texts[cols["hip"]]); hip=int(m.group(1)) if m else None
        if hip is None: continue
        star={"hip":hip}
        if "name" in cols and cols["name"]<len(cells):
            raw=re.sub(r'<[^>]+>','',cells[cols["name"]]).strip()
            if raw: star["name"]=raw
        if "mag" in cols and cols["mag"]<len(texts):
            try: star["mag"]=float(texts[cols["mag"]])
            except: pass
        if "spec" in cols and cols["spec"]<len(texts):
            m=re.search(r'([OBAFGKMLT]\d+(?:\.\d+)?(?:[IV]+(?:\s?[ab])?)?)',texts[cols["spec"]])
            if m: star["spec"]=m.group(1)
        if "ra" in cols and cols["ra"]<len(cells):
            raw=unescape(re.sub(r'<[^>]+>','',cells[cols["ra"]])).strip()
            parts=re.findall(r"(\d+)[h\s:]+(\d+)[m\s:]*(\d+(?:\.\d+)?)",raw)
            if parts: star["ra"]=[float(x) for x in parts[0]]
        if "dec" in cols and cols["dec"]<len(cells):
            raw=unescape(re.sub(r'<[^>]+>','',cells[cols["dec"]])).strip().replace("\u2212","-")
            parts=re.findall(r"([+-]?\d+)[°\s]+(\d+)[′\s]*(\d+(?:\.\d+)?)",raw)
            if parts: star["dec"]=[float(x) for x in parts[0]]
        stars.append(star)
    print(f"  Parsed {len(stars)} stars"); return stars

def find_cons(stel, name):
    name_l = name.lower()
    for cons in stel.get("constellations",[]):
        cn=cons.get("common_name",{})
        if cn.get("english","").lower()==name_l or cn.get("native","").lower()==name_l or cn.get("byname","").lower()==name_l:
            return cons
    return None

def best_month(ra_hours):
    sun_ra=(ra_hours+12)%24; m=int((sun_ra-6)/2)+1
    return max(1,min(12,m))

def fmt_pos(v):
    if isinstance(v,(list,tuple)) and len(v)>=3: return f"[{v[0]}, {v[1]}, {v[2]}]"
    return "[0,0,0]"

def build_entry(name):
    stel=fetch_stellarium(); wiki=fetch_wikipedia(name)
    sc=find_cons(stel,name)
    if not sc: print(f"  ERROR: '{name}' not found in Stellarium"); return None,[]
    lines=sc.get("lines",[]); print(f"  Stellarium lines: {len(lines)}")
    hip_stars={}
    for ws in wiki:
        h=ws["hip"]
        if h not in hip_stars or ws.get("mag",99)<hip_stars[h].get("mag",99):
            hip_stars[h]=ws
    line_hips=set()
    for ln in lines:
        for h in ln:
            if isinstance(h,int): line_hips.add(h)
    bright_hips={}
    for h in line_hips:
        ws=hip_stars.get(h)
        if ws and "mag" in ws and ws["mag"]<=MAG_CUT: bright_hips[h]=ws
    if not bright_hips:
        print("  ERROR: no bright stars matched between Wikipedia and Stellarium"); return None,[]

    kn=KNOWN.get(name)
    if kn:
        print("  Using verified connections from KNOWN config")
        known_hips={p[1]:p[0] for p in kn.get("main",[])}
        main_hips=[h for h in [p[1] for p in kn["main"]] if h in hip_stars]
        main_names=[known_hips[h] for h in main_hips]
        tag=kn["tag"]
        all_hips=main_hips.copy()
        rem=sorted([h for h in bright_hips if h not in main_hips],key=lambda h:bright_hips[h].get("mag",99))
        all_hips.extend(rem)
        rem2=sorted([h for h in hip_stars if h not in all_hips and "mag" in hip_stars[h] and hip_stars[h]["mag"]<=MAG_CUT],
                    key=lambda h:hip_stars[h]["mag"])
        all_hips.extend(rem2)
        conns=[]; mn=main_names
        for c in kn["conns"]:
            n1=mn[c[0]]; n2=mn[c[1]]
            c1={s.get("name",str(s["hip"])):i for i,s in enumerate([hip_stars.get(h) or bright_hips.get(h) for h in all_hips if hip_stars.get(h) or bright_hips.get(h)])}
            if n1 in c1 and n2 in c1: conns.append([c1[n1],c1[n2]])
    else:
        main_hips=sorted(bright_hips.keys(),key=lambda h:(bright_hips[h].get("ra",[99,0,0])[0],bright_hips[h].get("ra",[0,0,0])[1]))
        main_names=[bright_hips[h].get("name",str(h)) for h in main_hips]
        if len(main_hips)>12:
            longest=max(lines,key=lambda l:len([h for h in l if isinstance(h,int) and h in bright_hips]))
            main_hips=[h for h in longest if isinstance(h,int) and h in bright_hips]
            main_names=[bright_hips[h].get("name",str(h)) for h in main_hips]
        all_hips=main_hips.copy()
        rem=sorted([h for h in bright_hips if h not in main_hips],key=lambda h:bright_hips[h].get("mag",99))
        all_hips.extend(rem)
        rem2=sorted([h for h in hip_stars if h not in all_hips and "mag" in hip_stars[h] and hip_stars[h]["mag"]<=MAG_CUT],
                    key=lambda h:hip_stars[h]["mag"])
        all_hips.extend(rem2)
        mean_ra=sum(bright_hips[h].get("ra",[6,0,0])[0] for h in main_hips)/len(main_hips) if main_hips else 6
        tag=f'date: "{best_month(mean_ra):02d}/01"'
        hip_to_name={h:ws.get("name",str(h)) for h,ws in bright_hips.items()}
        conn_pairs=set()
        for ln in lines:
            flt=[h for h in ln if isinstance(h,int) and h in bright_hips]
            for i in range(len(flt)-1): conn_pairs.add((flt[i],flt[i+1]))
        conns=[]
        oidx={s.get("name",str(s["hip"])):i for i,s in enumerate([hip_stars.get(h) or bright_hips.get(h) for h in all_hips if hip_stars.get(h) or bright_hips.get(h)])}
        for a,b in conn_pairs:
            n1=hip_to_name.get(a); n2=hip_to_name.get(b)
            if n1 in oidx and n2 in oidx: conns.append([oidx[n1],oidx[n2]])

    ordered=[hip_stars.get(h) or bright_hips.get(h) for h in all_hips if hip_stars.get(h) or bright_hips.get(h)]
    # Override main star names with KNOWN config names (Wikipedia may use Bayer letters)
    if kn:
        known_map={p[1]:p[0] for p in kn.get("main",[])}
        for s in ordered:
            if s["hip"] in known_map: s["name"]=known_map[s["hip"]]
    oidx={s.get("name",str(s["hip"])):i for i,s in enumerate(ordered)}
    if kn:
        conns=[]
        mn=main_names
        for c in kn["conns"]:
            n1=mn[c[0]]; n2=mn[c[1]]
            if n1 in oidx and n2 in oidx: conns.append([oidx[n1],oidx[n2]])

    js=[]
    ck=name.upper().replace(" ","_")
    js.append(f'  {{ /* {ck} */')
    js.append(f'    name: "{name}", {tag},')
    js.append(f'    stars: [')
    for s in ordered:
        ra=fmt_pos(s.get("ra")); dec=fmt_pos(s.get("dec"))
        spec="null" if s.get("spec") is None else json.dumps(s["spec"])
        nm=s.get("name",str(s["hip"]))
        js.append(f'      {{ name:{json.dumps(nm)}, ra:{ra}, dec:{dec}, mag:{s["mag"]:.2f}, spec:{spec} }},')
    js.append(f'    ],')
    js.append(f'    connections: {json.dumps(conns)},')
    js.append(f'    mainIndices: {json.dumps(list(range(len(main_hips))))},')
    js.append(f'  }},')
    print(f"  Main stars: {main_names}")
    return "\n".join(js), ordered

def update_shared(ck, entry):
    with open(SHARED_JS) as f: c=f.read()
    p=r'{ /\* '+ck+r' \*/(.*?)\n  },'
    m=re.search(p,c,re.DOTALL)
    if m: c=c[:m.start()]+entry+c[m.end():]
    else: c=c.replace("];",entry+"\n];")
    with open(SHARED_JS,"w") as f: f.write(c)
    print(f"  Updated {SHARED_JS}")

if __name__=="__main__":
    args=sys.argv[1:]
    if "--list" in args:
        for cons in fetch_stellarium().get("constellations",[]):
            cn=cons.get("common_name",{}); eng=cn.get("english","")
            nat=cn.get("native","")
            if eng or nat: print(f"  {eng or nat}")
        sys.exit(0)
    targets=list(KNOWN.keys()) if "--all" in args else [" ".join(a.capitalize() for a in arg.split()) for arg in args]
    targets=[t for t in targets if t]
    if not targets:
        print(f"Usage: {sys.argv[0]} Orion\n       {sys.argv[0]} --all\n       {sys.argv[0]} --list"); sys.exit(1)
    for name in targets:
        print(f"\n=== {name.upper()} ==="); entry_js,_=build_entry(name)
        if entry_js: update_shared(name.upper().replace(" ","_"),entry_js)
    print("\nDone.")