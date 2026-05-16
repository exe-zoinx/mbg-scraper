# 🥘 MBG Case Tracker — Indonesia

Mass food-poisoning incidents from Indonesia's **Makan Bergizi Gratis** (Free Nutritious Meal) program, scraped from [Wikipedia](https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis).

**35 provinces · 689 incidents · 2 with deaths**

## Data

```bash
python scraper.py
```

Output: `data/mbg_cases.json` — zero deps (stdlib + curl/wget).

### Structure

```jsonc
{
  "metadata": {
    "title": "Kasus keracunan massal program Makan Bergizi Gratis",
    "source": "https://id.wikipedia.org/wiki/...",
    "scraped_at": "2026-05-16T14:00:00Z",
    "license": "CC-BY-SA 3.0 (via Wikipedia)",
    "stats": {
      "total_incidents": 689,
      "provinces_affected": 35,
      "incidents_by_province": { "Jawa Barat": 123, ... },
      "incidents_with_deaths": 2
    }
  },
  "cases": [
    {
      "date": "29 September 2025",
      "province": "Nanggroe Aceh Darussalam",
      "regency": "Kabupaten Aceh Utara",
      "school": "SDN 6 Matangkuli",
      "symptomatic": "3 Siswa",
      "deaths": "",
      "references": ["https://..."]
    }
  ]
}
```

## Schedule

Weekly refresh via GitHub Actions (Sunday 06:00 UTC). Also triggerable manually.

## Caveats

- **Rowspan clustering:** A single incident covering 4 schools shows the same `symptomatic` count for each — they're 4 venues under one event, not separate victims.
- **TBA / tidak disebutkan** = Wikipedia didn't have the data.
- **References** only appear on the first row of a rowspan group.
