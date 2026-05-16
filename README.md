# 🥘 MBG Case Tracker — Indonesia

Mass food-poisoning incidents from Indonesia's **Makan Bergizi Gratis** program, scraped from [Wikipedia](https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis).

## Quick start

```bash
python scraper.py        # generate data/mbg_cases.json
python geocode.py        # add lat/lng to data/mbg_cases.json
```

Zero external deps — stdlib + curl/wget.

## Data

### Format

```jsonc
{
  "date": "29 September 2025",
  "province": "Nanggroe Aceh Darussalam",
  "regency": "Kabupaten Aceh Utara",
  "school": "SDN 6 Matangkuli",
  "symptomatic": 3,                    // int, original incident total
  "unit": "siswa",                      // siswa | santri | warga | orang
  "deaths": "",
  "deaths_count": null,
  "tags": ["keracunan"],               // keracunan | deaths | sppg
  "symptomatic_approximate": false,    // true = shared via rowspan
  "symptomatic_per_school": null,      // divided estimate when approximate
  "lat": 4.991569,                     // regency centroid + jitter
  "lng": 97.157298                     // ~200m spread to prevent overlap
}
```

### Totals

| Metric | Value |
|---|---|
| School venues | **687** |
| Unique incidents | **375** |
| Provinces | **38** |
| Symptomatic victims | **32,923** |
| Fatalities | **3** |
| Geocoded entries | **687/687** |

### Geocoding

Coordinates resolved via [Nominatim](https://nominatim.openstreetmap.org/):
- **Regency level** (default): centroid of the regency/city
- **Province level** (fallback): 5 entries with no regency match
- **Jitter**: ±0.002° (~200m) random offset applied per entry to prevent visual overlap on maps (687 unique coordinate pairs)

Cache saved to `data/geocache.json` — subsequent runs are instant.

```bash
python geocode.py   # 1st run: ~6 min (207 queries at 1 req/sec nominatim)
python geocode.py   # 2nd run: instant (all cached)
```

### Tags

| Tag | Count | Meaning |
|---|---|---|
| `keracunan` | 687 | Poisoning incident |
| `deaths` | 3 | Fatalities |
| `sppg` | 27 | SPPG/BGN-related news |

### Rowspan division

Shared incident counts divided equally per school:

```jsonc
{"symptomatic": 33, "symptomatic_per_school": 16, "symptomatic_approximate": true}
```

## Schedule

Weekly refresh via GitHub Actions (Sunday 06:00 UTC).
Geocode step included — data always shipped with coordinates.
