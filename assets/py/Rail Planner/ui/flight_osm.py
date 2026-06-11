from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import List

import osmium

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"


class _RunwayExtractor(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []

    def way(self, w):
        tag = w.tags.get("aeroway")
        if tag in ("runway", "taxiway"):
            coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
            if len(coords) >= 2:
                self.ways.append({"id": w.id, "coords": coords, "tags": {"aeroway": tag}})


def extract_runways_from_pbf(pbf_path: Path, out_cache: Path) -> List[dict]:
    log.info("Extracting runways from %s", pbf_path)
    extractor = _RunwayExtractor()
    extractor.apply_file(str(pbf_path), locations=True)
    ways = extractor.ways
    try:
        out_cache.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(out_cache, "wt") as f:
            json.dump({"ways": ways}, f)
        log.info("Saved runway cache %s (%d ways)", out_cache, len(ways))
    except Exception as e:
        log.warning("Failed to save runway cache: %s", e)
    return ways


def load_runway_cache(cache_path: Path):
    try:
        with gzip.open(cache_path, "rt") as f:
            raw = json.load(f)
        return raw.get("ways", [])
    except Exception as e:
        log.debug("Could not read runway cache %s: %s", cache_path, e)
        return []


class _GateExtractor(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.gates = []

    def node(self, n):
        # capture nodes tagged aeroway=gate
        if n.tags.get("aeroway") == "gate":
            if n.location.valid():
                self.gates.append({"id": n.id, "lat": n.location.lat, "lon": n.location.lon, "tags": dict(n.tags)})

    def way(self, w):
        # capture ways tagged aeroway=gate or aeroway=apron (use centroid)
        tag = w.tags.get("aeroway")
        if tag in ("gate", "apron"):
            coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
            if coords:
                # compute simple centroid
                lat = sum(p[0] for p in coords) / len(coords)
                lon = sum(p[1] for p in coords) / len(coords)
                self.gates.append({"id": w.id, "lat": lat, "lon": lon, "tags": dict(w.tags)})


def extract_gates_from_pbf(pbf_path: Path, out_cache: Path) -> List[dict]:
    log.info("Extracting gates/aprons from %s", pbf_path)
    extractor = _GateExtractor()
    extractor.apply_file(str(pbf_path), locations=True)
    gates = extractor.gates
    try:
        out_cache.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(out_cache, "wt") as f:
            json.dump({"gates": gates}, f)
        log.info("Saved gate cache %s (%d gates)", out_cache, len(gates))
    except Exception as e:
        log.warning("Failed to save gate cache: %s", e)
    return gates


def load_gate_cache(cache_path: Path) -> List[dict]:
    try:
        with gzip.open(cache_path, "rt") as f:
            raw = json.load(f)
        return raw.get("gates", [])
    except Exception as e:
        log.debug("Could not read gate cache %s: %s", cache_path, e)
        return []
