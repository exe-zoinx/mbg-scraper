#!/usr/bin/env python3
"""
MBG Geocoder v2 — adds lat/lng to mbg_cases.json.

Strategy (fast, practical):
  1. Query each UNIQUE regency+province combo via Nominatim (~207 queries)
  2. All schools in that regency inherit the regency centroid
  3. Small jitter (±0.002°) applied per entry so points don't overlap on map
  4. Province centroid as last resort
  5. Results cached in data/geocache.json (instant re-run)

~20 min for first run, instant thereafter.
"""

import json, random, re, subprocess, sys, time, urllib.parse
from collections import defaultdict
from pathlib import Path

USER_AGENT = "MBGScraperGeocoder/2.0"
NOM_URL = "https://nominatim.openstreetmap.org/search"
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "mbg_cases.json"
CACHE_FILE = DATA_DIR / "geocache.json"
JITTER = 0.002  # ~200m — enough to separate points on zoomed map

PROVINCE_CENTROIDS = {
    "nanggroe aceh darussalam": (4.5, 96.5), "sumatera utara": (2.5, 99.0),
    "sumatera barat": (-0.5, 100.5), "riau": (0.5, 102.0),
    "kepulauan riau": (1.0, 104.5), "jambi": (-1.5, 102.5),
    "sumatera selatan": (-3.0, 104.0), "bangka belitung": (-2.5, 106.0),
    "bengkulu": (-3.5, 102.0), "lampung": (-5.0, 105.0),
    "banten": (-6.0, 106.0), "dki jakarta": (-6.2, 106.8),
    "jawa barat": (-6.8, 107.5), "jawa tengah": (-7.5, 110.0),
    "daerah istimewa yogyakarta": (-7.8, 110.4), "jawa timur": (-7.5, 112.5),
    "bali": (-8.3, 115.0), "nusa tenggara barat": (-8.5, 117.0),
    "nusa tenggara timur": (-9.5, 121.0), "kalimantan barat": (0.0, 110.0),
    "kalimantan tengah": (-2.0, 113.5), "kalimantan selatan": (-3.0, 115.0),
    "kalimantan timur": (0.5, 116.5), "kalimantan utara": (3.0, 116.5),
    "sulawesi utara": (1.0, 124.5), "gorontalo": (0.5, 122.5),
    "sulawesi tengah": (-1.0, 121.0), "sulawesi barat": (-2.5, 119.5),
    "sulawesi selatan": (-4.0, 120.0), "sulawesi tenggara": (-4.0, 122.5),
    "maluku utara": (1.0, 127.5), "maluku": (-3.0, 129.0),
    "papua barat daya": (-1.0, 131.0), "papua barat": (-1.0, 133.0),
    "papua": (-3.0, 135.0), "papua tengah": (-3.5, 136.0),
    "papua pegunungan": (-4.0, 138.0), "papua selatan": (-6.0, 139.0),
}


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def save_cache(cache: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def query_nominatim(q: str):
    """One Nominatim query via curl (much faster than urllib in this env)."""
    params = urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "accept-language": "id"})
    url = f"{NOM_URL}?{params}"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "10", "-A", USER_AGENT, url],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            if data and "lat" in data[0]:
                return (float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("type", ""))
    except: pass
    return None

def regency_key(regency: str, province: str) -> str:
    return f"{regency}|{province}"

def make_entry_key(school: str, regency: str, province: str) -> str:
    return f"{school}|{regency}|{province}"


def main():
    if not DATA_FILE.exists():
        print("❌ Run scraper first.", file=sys.stderr)
        return

    data = json.loads(DATA_FILE.read_text())
    cases = data["cases"]
    cache = load_cache()

    # Collect unique regency+province keys
    regency_keys: set[str] = set()
    for c in cases:
        rk = regency_key(c.get("regency", ""), c.get("province", ""))
        regency_keys.add(rk)

    new_keys = [rk for rk in regency_keys if rk not in cache]
    print(f"📍 {len(cases)} entries | {len(regency_keys)} regencies | {len(regency_keys) - len(new_keys)} cached | {len(new_keys)} new", file=sys.stderr)
    if new_keys:
        print(f"   ~{len(new_keys) * 6:.0f}s ≈ {len(new_keys) * 6 // 60}m", file=sys.stderr)

    # Query each NEW regency once
    for idx, rk in enumerate(new_keys, 1):
        regency, province = rk.split("|", 1)
        q = f"{regency}, {province}, Indonesia"
        print(f"  [{idx}/{len(new_keys)}] {q[:70]}", file=sys.stderr)
        result = query_nominatim(q)
        time.sleep(1.05)
        cache[rk] = result
        if idx % 50 == 0:
            save_cache(cache)

    save_cache(cache)

    # Assign coords with jitter
    hist: dict = {}
    reg_lvl = prov_lvl = failed = 0

    for c in cases:
        rk = regency_key(c["regency"], c["province"])
        coord = cache.get(rk)

        if coord:
            lat, lng, _ = coord
        else:
            cent = PROVINCE_CENTROIDS.get(c["province"].strip().lower())
            if cent:
                lat, lng = cent
                prov_lvl += 1
            else:
                c["lat"] = None
                c["lng"] = None
                failed += 1
                continue

        # Jitter to prevent visual overlap
        key = (round(lat, 3), round(lng, 3))
        n = hist.get(key, 0)
        jlat = random.uniform(-JITTER, JITTER) * (n + 1)
        jlng = random.uniform(-JITTER, JITTER) * (n + 1)
        hist[key] = n + 1

        c["lat"] = round(lat + jlat, 6)
        c["lng"] = round(lng + jlng, 6)
        reg_lvl += 1

    print(f"\n✅ {reg_lvl + prov_lvl}/{len(cases)} geocoded", file=sys.stderr)
    print(f"   Regency-level: {reg_lvl} | Province-level: {prov_lvl} | Failed: {failed}", file=sys.stderr)

    data.setdefault("meta", {}).setdefault("stats", {})["geocoded"] = reg_lvl + prov_lvl
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"💾 {DATA_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
