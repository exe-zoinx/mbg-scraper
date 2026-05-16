# 🥘 MBG Case Tracker

**Makan Bergizi Gratis** — scattered mass food-poisoning incidents from Indonesia's free school meal program, India's Midday Meal Scheme, South Korea's school meals, and China's equivalent.

This scraper downloads and parses the [Wikipedia article](https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis) into clean JSON for public consumption.

## Data

| Section | Source | Count |
|---|---|---|
| India — Midday Meal Scheme | Wikipedia | 4 incidents |
| Indonesia — Makan Bergizi Gratis | Wikipedia | 688 incidents across 35 provinces |
| Korea Selatan — School meals | Wikipedia | 3 incidents |
| Tiongkok — School meal program | Wikipedia | 1 incident |

**License:** CC-BY-SA 3.0 (via Wikipedia)

## Usage

```bash
python scraper.py
```

Output: `data/mbg_cases.json`

Zero dependencies — only needs Python 3.10+ and `curl` or `wget` at runtime.

## JSON structure

```jsonc
{
  "metadata": {
    "title": "...",
    "source_url": "https://id.wikipedia.org/wiki/...",
    "scraped_at": "2026-05-16T14:00:00Z",
    "total_cases": 696,
    "data_license": "CC-BY-SA 3.0 (via Wikipedia)",
    "stats": {
      "total_incidents": 688,
      "provinces_affected": 35,
      "incidents_by_province": { "Jawa Barat": 123, ... },
      "incidents_with_deaths": 2
    }
  },
  "cases": {
    "india": [ ... ],
    "indonesia_mbg": [
      {
        "date": "29 September 2025",
        "province": "Nanggroe Aceh Darussalam",
        "regency": "Kabupaten Aceh Utara",
        "school": "SDN 6 Matangkuli",
        "symptomatic": "3 Siswa",
        "deaths": "",
        "references": ["https://..."]
      },
      ...
    ],
    "korea_selatan": [ ... ],
    "tiongkok": [ ... ]
  }
}
```

## Caveats

- **Rowspan handling:** Wikipedia wiki-tables use `rowspan` extensively. The parser resolves them but multi-school clustering means some counts appear duplicated across schools in the same incident (e.g., 150 students spread across 4 schools).
- **References:** Only the first row in a rowspan group carries the citation URL; subsequent rows under the same reference will have empty `references[]`. Check Wikipedia for the canonical citation.
- **"TBA (Tidak disebutkan)"** values mean the Wikipedia article didn't have the data.

## Schedule

Data refreshes weekly via GitHub Actions (Sunday 06:00 UTC).
Manual trigger: `gh workflow run update-data.yml`
