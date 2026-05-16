# 🥘 MBG Case Tracker — Indonesia

Mass food-poisoning incidents from Indonesia's **Makan Bergizi Gratis** program, scraped from [Wikipedia](https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis).

## Totals

| Metric | Value |
|---|---|
| School venues affected | **687** |
| Unique incidents | **375** |
| Provinces | **38** |
| Symptomatic victims | **32,923** |
| Fatalities | **3** |
| Approximate (rowspan-divided) | 422 entries |
| Tagged SPPG | 27 entries |

> Wikipedia's stated ~11,390 total is outdated — more cases added since.

## Data

```bash
python scraper.py
```

Output: `data/mbg_cases.json` — zero deps.

### Entry format

```jsonc
{
  "date": "29 September 2025",
  "province": "Nanggroe Aceh Darussalam",
  "regency": "Kabupaten Aceh Utara",
  "school": "SDN 6 Matangkuli",
  "symptomatic": 3,              // integer count (original incident total)
  "unit": "siswa",                // siswa | santri | warga | orang
  "deaths": "",
  "deaths_count": null,
  "tags": ["keracunan"],
  "symptomatic_approximate": false,  // true = shared via rowspan
  "symptomatic_per_school": null     // divided estimate when approximate
}
```

### Tags

| Tag | Meaning | Count |
|---|---|---|
| `keracunan` | Poisoning incident | 687 |
| `deaths` | Fatalities involved | 3 |
| `sppg` | SPPG/BGN-related news | 27 |

### Rowspan division

When Wikipedia groups one incident across multiple schools with a shared count (rowspan), the total is kept in `symptomatic` and each school gets an estimated per-school value:

```jsonc
{
  "symptomatic": 33,              // original total
  "symptomatic_per_school": 16,   // rounded division
  "symptomatic_approximate": true
}
```

## Schedule

Weekly via GitHub Actions (Sunday 06:00 UTC).
