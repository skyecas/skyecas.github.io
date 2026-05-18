from __future__ import annotations
from pathlib import Path
import json
import re
import yaml
from typing import Any


def _cache_path(path: Path) -> Path:
    return path.with_suffix(".json")


def _read_cache(path: Path) -> dict[str, Any] | None:
    cache = _cache_path(path)
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text())
        src_mtime = path.stat().st_mtime
        if data.get("_source_mtime") == src_mtime:
            data.pop("_source_mtime", None)
            data.pop("_cached_at", None)
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def write_post_cache(path: Path, data: dict[str, Any]) -> None:
    cache = _cache_path(path)
    try:
        src_mtime = path.stat().st_mtime
    except OSError:
        return
    cache_data = {**data, "_source_mtime": src_mtime, "_cached_at": __import__("time").time()}
    cache.write_text(json.dumps(cache_data, indent=2, default=str))


def save_route_cache(path: Path, route_data: dict[str, Any], curation_data: dict[str, Any]) -> None:
    """Merge full route + curation data into the JSON cache alongside markdown metadata."""
    cache = _cache_path(path)
    existing = {}
    if cache.exists():
        try:
            existing = json.loads(cache.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    existing["route_data"] = route_data
    existing["curation_data"] = curation_data
    # Promote curation fields to top level for frontend compatibility
    existing["title"] = curation_data.get("title", existing.get("title", ""))
    existing["date"] = curation_data.get("date", existing.get("date", ""))
    existing["description"] = curation_data.get("description", existing.get("description", ""))
    existing["tags"] = curation_data.get("tags", existing.get("tags", []))
    existing["category"] = curation_data.get("category", existing.get("category", "train-travel"))
    existing["destination_notes"] = curation_data.get("destination_notes", existing.get("destination_notes", ""))
    existing["overall_notes"] = curation_data.get("overall_notes", existing.get("overall_notes", ""))
    existing["trains_notes"] = curation_data.get("trains_notes", existing.get("trains_notes", ""))
    existing["stations_notes"] = curation_data.get("stations_notes", existing.get("stations_notes", ""))
    existing["countries"] = curation_data.get("countries", existing.get("countries", []))
    existing["outbound_label"] = curation_data.get("outbound_label", existing.get("outbound_label", "Outbound"))
    existing["inbound_label"] = curation_data.get("inbound_label", existing.get("inbound_label", "Inbound"))
    existing["outbound_journey_origin"] = curation_data.get("outbound_journey_origin", existing.get("outbound_journey_origin", ""))
    existing["outbound_journey_dest"] = curation_data.get("outbound_journey_dest", existing.get("outbound_journey_dest", ""))
    existing["inbound_journey_origin"] = curation_data.get("inbound_journey_origin", existing.get("inbound_journey_origin", ""))
    existing["inbound_journey_dest"] = curation_data.get("inbound_journey_dest", existing.get("inbound_journey_dest", ""))
    # Collect all photos from leg curations for the global photos list
    all_photos = set(existing.get("photos", []))
    for lc in curation_data.get("leg_curations", []):
        for p in lc.get("photos", []):
            all_photos.add(p)
    existing["photos"] = sorted(all_photos)
    existing.setdefault("directions", {})

    try:
        src_mtime = path.stat().st_mtime
    except OSError:
        return
    existing["_source_mtime"] = src_mtime
    existing["_cached_at"] = __import__("time").time()

    cache.write_text(json.dumps(existing, indent=2, default=str))


def parse_post(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    cached = _read_cache(path)
    if cached is not None:
        return cached

    text = path.read_text()

    frontmatter, body = _parse_frontmatter(text)
    if not frontmatter:
        return None

    title = frontmatter.get("title", "")
    date = str(frontmatter.get("date", ""))[:10]
    description = frontmatter.get("description", "")
    tags = frontmatter.get("tags", "")
    category = frontmatter.get("categories", "train-travel")

    if isinstance(tags, str):
        tags = tags.split()

    dest_notes = ""
    overall_notes = ""
    trains_notes = ""
    stations_notes = ""
    countries: list[str] = []
    outbound_name = "Outbound"
    inbound_name = "Inbound"

    directions: dict[str, list[dict]] = {"outbound": [], "inbound": []}
    current_dir = None
    body_lines = body.split("\n")

    in_summary = False
    for line_idx, line in enumerate(body_lines):
        if line.startswith("# Location"):
            current_dir = None
            in_summary = False
        elif line.startswith("# Summary") or line.startswith("# Sumamry"):
            current_dir = None
            in_summary = True
        elif line.startswith("# ") and "Outbound" in line:
            current_dir = "outbound"
            in_summary = False
            outbound_name = line.lstrip("#").strip()
        elif line.startswith("# ") and "Inbound" in line:
            current_dir = "inbound"
            in_summary = False
            inbound_name = line.lstrip("#").strip()
        elif current_dir and line.startswith("## "):
            section = _parse_section(body_lines, line_idx, current_dir)
            if section:
                directions[current_dir].append(section)
        elif in_summary and line.startswith("Trains:"):
            trains_notes = line[len("Trains:"):].strip()
        elif in_summary and line.startswith("Stations:"):
            stations_notes = line[len("Stations:"):].strip()
        elif in_summary and line.startswith("Destination:"):
            overall_notes = line[len("Destination:"):].strip()
        elif in_summary and line.startswith("Countries:"):
            m = re.search(r'\(([^)]+)\)', line)
            if m:
                countries = [c.strip() for c in m.group(1).split(",") if c.strip()]

    all_photos = []
    for dir_name, sections in directions.items():
        for s in sections:
            for p in s.get("photos", []):
                if p not in all_photos:
                    all_photos.append(p)

    # Derive journey origin/dest from first/last section in each direction
    outbound_journey_origin = ""
    outbound_journey_dest = ""
    inbound_journey_origin = ""
    inbound_journey_dest = ""
    for dir_key in ["outbound", "inbound"]:
        sections = directions.get(dir_key, [])
        if not sections:
            continue
        origin = sections[0]["name"]
        last_table = sections[-1].get("table", [])
        dest = last_table[-1]["destination"] if last_table else ""
        if dir_key == "outbound":
            outbound_journey_origin = origin
            outbound_journey_dest = dest
        else:
            inbound_journey_origin = origin
            inbound_journey_dest = dest

    result = {
        "title": title,
        "date": date,
        "description": description,
        "tags": tags,
        "category": category,
        "destination_notes": dest_notes,
        "overall_notes": overall_notes,
        "trains_notes": trains_notes,
        "stations_notes": stations_notes,
        "countries": countries,
        "outbound_label": outbound_name,
        "inbound_label": inbound_name,
        "outbound_journey_origin": outbound_journey_origin,
        "outbound_journey_dest": outbound_journey_dest,
        "inbound_journey_origin": inbound_journey_origin,
        "inbound_journey_dest": inbound_journey_dest,
        "directions": directions,
        "photos": all_photos,
    }
    write_post_cache(path, result)
    return result


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        front = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        front = {}
    return front or {}, match.group(2)


def _parse_section(lines: list[str], start_idx: int, direction: str) -> dict | None:
    header_line = lines[start_idx]
    section_name = header_line.lstrip("##").strip()

    section_lines = []
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("## ") or (lines[i].startswith("# ") and not lines[i].startswith("## ")):
            break
        section_lines.append(lines[i])

    content = "\n".join(section_lines)

    table = _parse_table(content)
    notes = _parse_notes(content)
    photos = _parse_photos(content)

    return {
        "name": section_name,
        "table": table,
        "notes": notes,
        "photos": photos,
    }


def _normalize_time(raw: str) -> str:
    """Extract the last valid HH:MM or HH.MM time from a cell, stripping HTML."""
    cleaned = re.sub(r"<[^>]+>", "", raw)
    cleaned = re.sub(r"~~.*?~~", "", cleaned)
    matches = re.findall(r"\b(\d{1,2})[.:](\d{2})\b", cleaned)
    if not matches:
        return ""
    h, m = matches[-1]
    return f"{int(h):02d}:{m}"


def _parse_table(text: str) -> list[dict]:
    lines = text.strip().split("\n")
    table_start = None
    for i, line in enumerate(lines):
        if line.startswith("| Departure |"):
            table_start = i
            break
    if table_start is None:
        return []

    rows = []
    for line in lines[table_start + 2:]:
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            break
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 3:
            rows.append({
                "departure": _normalize_time(parts[0]),
                "arrival": _normalize_time(parts[1]),
                "destination": re.sub(r"\s*\(walk\)\s*$", "", parts[2]),
                "walk": "(walk)" in parts[2],
            })

    return rows


def _parse_notes(text: str) -> str:
    lines = text.strip().split("\n")
    in_table = False
    past_table = False
    notes_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("| Departure |"):
            in_table = True
            continue
        if in_table and stripped.startswith("| :"):
            continue
        if in_table and stripped.startswith("|"):
            continue
        if in_table:
            in_table = False
            past_table = True

        if past_table and stripped:
            if stripped.startswith("<swiper"):
                break
            if stripped.startswith("</swiper"):
                break
            if stripped.startswith("{% include"):
                continue
            notes_lines.append(stripped)

    notes = " ".join(notes_lines).strip()
    return notes


def _parse_photos(text: str) -> list[str]:
    photos = []
    pattern = r'path="assets/img/[^"]+/([^"]+)"'
    for match in re.finditer(pattern, text):
        photos.append(match.group(1))
    return photos


def list_sprint_posts(posts_dir: Path) -> list[dict]:
    if not posts_dir.is_dir():
        return []

    posts = []
    for f in sorted(posts_dir.glob("*-sprint.md"), reverse=True):
        text = f.read_text()
        fm, _ = _parse_frontmatter(text)
        posts.append({
            "path": str(f.relative_to(posts_dir.parent)),
            "filename": f.name,
            "title": fm.get("title", f.name),
            "date": str(fm.get("date", ""))[:10],
        })
    return posts
