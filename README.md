# 🥘 MBG Case Tracker — Indonesia

Mass food-poisoning incidents from Indonesia's **Makan Bergizi Gratis** program, scraped from [Wikipedia](https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis).

## Totals

| Metric | Value |
|---|---|
| School venues affected | **687** |
| Provinces | **38** |
| Total symptomatic victims | **216,596** |
| Fatalities | **3** |
| Approximate (rowspan-divided) entries | 420 |
| Cases with SPPG flag | 27 |

## Data

```bash
python scraper.py             # regenerate data/mbg_cases.json
```

Zero deps — stdlib + curl/wget.

### Entry format

```jsonc
{
  "date": "29 September 2025",
  "province": "Nanggroe Aceh Darussalam",
  "regency": "Kabupaten Aceh Utara",
  "school": "SDN 6 Matangkuli",
  "symptomatic": "3 Siswa",              // numeric count + unit
  "deaths": "",                           // filled if fatalities occurred
  "references": ["https://..."],
  "tags": ["keracunan"],                  // categories
  "deaths_count": null,                   // numeric parse of deaths, if any
  "symptomatic_approximate": false        // true = divided from rowspan group
}
```

### Tags

| Tag | Meaning | Count |
|---|---|---|
| `keracunan` | Poisoning incident (default) | 687 |
| `deaths` | Incident involved fatalities | 3 |
| `sppg` | SPPG/BGN-related news | 27 |

> `kecelakaan` (accidents outside poisoning) not available from this Wikipedia table.

### Rowspan division

When Wikipedia groups a single incident across multiple schools with one shared victim count (`rowspan`), the count is **divided equally** and marked `symptomatic_approximate: true`:

```
"5 Mei 2025" → 174 Siswa ÷ 14 schools → "12.4 Siswa" each
```

## Schedule

Weekly via GitHub Actions (Sunday 06:00 UTC) + manual trigger.
