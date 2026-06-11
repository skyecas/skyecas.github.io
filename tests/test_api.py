import json

from fastapi.testclient import TestClient

from assets.py.Rail Planner.ui import server as srv  # module under test


client = TestClient(srv.app)


def test_estimate_emissions_fields():
    payload = {
        "legs": [
            {
                "index": 0,
                "mode": "RAIL",
                "operator": "DB",
                "distance_km": 100,
                "distance_source": "scheduled",
                "countries": ["DE"],
            }
        ]
    }
    r = client.post("/api/estimate-emissions", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "legs" in data
    leg = data["legs"][0]
    # Basic expected fields from EmissionsEstimate.to_dict()
    expected_keys = {
        "index",
        "kg",
        "min_kg",
        "max_kg",
        "rate_g_per_km",
        "rate_min_g_per_km",
        "rate_max_g_per_km",
        "confidence",
        "distance_source",
        "traction",
        "countries",
        "assumptions",
    }
    assert expected_keys.issubset(set(leg.keys()))


def test_enrich_geometry_returns_traction_hint(monkeypatch):
    # Monkeypatch the internal _enrich_one_leg to avoid OSM dependency
    def fake_enrich_one_leg(leg_in: dict) -> dict:
        return {
            "index": leg_in.get("index", 0),
            "geometry": [{"lat": 51.0, "lon": 0.0}, {"lat": 52.0, "lon": 1.0}],
            "source": "railway_db",
            "traction_hint": "electric",
        }

    monkeypatch.setattr(srv, "_enrich_one_leg", fake_enrich_one_leg)
    payload = {"legs": [{"index": 0}]}
    r = client.post("/api/enrich-geometry", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "legs" in data
    leg = data["legs"][0]
    assert leg.get("traction_hint") == "electric"


def test_emissions_vary_with_traction_hint():
    base = {
        "index": 0,
        "mode": "RAIL",
        "operator": "",
        "distance_km": 200,
        "distance_source": "scheduled",
        "countries": ["DE", "FR"],
    }
    r1 = client.post("/api/estimate-emissions", json={"legs": [{**base, "traction_hint": "diesel"}]})
    r2 = client.post("/api/estimate-emissions", json={"legs": [{**base, "traction_hint": "electric"}]})
    assert r1.status_code == 200 and r2.status_code == 200
    l1 = r1.json()["legs"][0]
    l2 = r2.json()["legs"][0]
    # Different traction hints should produce different estimates (rates or totals)
    assert (l1.get("kg") != l2.get("kg")) or (
        l1.get("rate_g_per_km") != l2.get("rate_g_per_km")
    )
