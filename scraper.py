#!/usr/bin/env python3
"""
MBG (Makan Bergizi Gratis) Case Scraper
========================================
Scrapes Wikipedia for mass food-poisoning incidents from Indonesia's
Makan Bergizi Gratis free school meal program. Outputs clean JSON.

Source: https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis
"""

import json
import re
import subprocess
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

WIKI_URL = (
    "https://id.wikipedia.org/w/index.php?title="
    "Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis&action=raw"
)
USER_AGENT = "MBGScraper/1.0"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "mbg_cases.json"
COLUMNS = ["date", "province", "regency", "school", "symptomatic", "deaths"]

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_wikitext(url: str) -> str:
    for cmd in [
        ["curl", "-sL", "--max-time", "25", "-A", USER_AGENT, url],
        ["wget", "-qO-", "--timeout=25", url],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    raise RuntimeError("Failed to fetch wikitext")

# ---------------------------------------------------------------------------
# Text cleaners
# ---------------------------------------------------------------------------

def clean_val(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = text.replace("'''", "").replace("''", "").replace("\u00a0", " ")
    text = re.sub(r"\{\{[^}]*}}", "", text)
    text = text.replace("[[", "").replace("]]", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"'}\[\]\\,;|]+", text)

# ---------------------------------------------------------------------------
# Rowspan-aware wikitable parser
# ---------------------------------------------------------------------------

def parse_table_rows(body: str) -> tuple[list[list[str]], list[str]]:
    """Return (parsed_rows, raw_segments)."""
    segs = re.split(r"\n\|-\s*\n", body)
    data_segs = [s for s in segs if re.search(r"(?<!\|)\|[^|!+\-]", s)]

    rows: list[list[str]] = []
    span: dict[int, dict] = {}

    for seg in data_segs:
        cells = []
        for line in seg.split("\n"):
            line = line.strip()
            if not line.startswith("|") or line.startswith("|-|+|!") or line.startswith("|!"):
                continue
            cell = re.sub(r"^\|+", "", line).strip()
            cells.append(cell)

        row: list[str] = []
        col = 0
        ci = 0
        while ci < len(cells) or col < len(COLUMNS):
            if col in span and span[col]["r"] > 0:
                row.append(span[col]["v"])
                span[col]["r"] -= 1
                if span[col]["r"] <= 0:
                    del span[col]
                col += 1
                continue
            if ci >= len(cells):
                break
            raw = cells[ci]
            rs = 1
            m = re.search(r'rowspan\s*=\s*["\']?(\d+)', raw)
            if m:
                rs = int(m.group(1))
            val_raw = re.sub(r"^[\|]+", "", raw)
            val_raw = re.sub(r'\s*rowspan\s*=\s*["\']?\d+["\']?\s*', "", val_raw)
            if "|" in val_raw:
                val_raw = val_raw.rsplit("|", 1)[-1]
            val = clean_val(val_raw)
            row.append(val)
            if rs > 1:
                span[col] = {"r": rs - 1, "v": val}
            ci += 1
            col += 1
        rows.append(row)

    return rows, data_segs


def extract_mbg_table(wikitext: str) -> list[dict]:
    start = wikitext.find('{| class="wikitable"')
    if start == -1:
        return []
    rest = wikitext[start:]
    end = rest.find("\n|}")
    if end == -1:
        return []
    table_raw = rest[:end]

    rows, raw_segs = parse_table_rows(table_raw)
    entries = []

    for i, row in enumerate(rows):
        e = {}
        for j, col in enumerate(COLUMNS):
            e[col] = row[j] if j < len(row) else ""
        if e["date"].startswith("Tanggal") or e["province"].startswith("Provinsi"):
            continue
        if e["date"] in ("+", "TOTAL"):
            continue
        if all(not e[c] for c in COLUMNS):
            continue
        for field in ("deaths", "symptomatic"):
            if "access-date" in e[field] or "url=" in e[field] or "{{" in e[field] or "}}" in e[field]:
                e[field] = ""
        for c in COLUMNS:
            e[c] = e[c].replace("{{", "").replace("}}", "")
        e["references"] = extract_urls(raw_segs[i]) if i < len(raw_segs) else []
        entries.append(e)

    return entries

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def compute_stats(cases: list[dict]) -> OrderedDict:
    provs = defaultdict(int)
    deaths = 0
    for c in cases:
        p = c["province"] or "Tidak diketahui"
        provs[p] += 1
        if c["deaths"] not in ("", "–", "-", "0"):
            deaths += 1
    return OrderedDict([
        ("total_incidents", len(cases)),
        ("provinces_affected", len(provs)),
        ("incidents_by_province", OrderedDict(sorted(provs.items(), key=lambda x: -x[1]))),
        ("incidents_with_deaths", deaths),
    ])

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    print("🕸  MBG Scraper — fetching...", file=sys.stderr)
    wt = fetch_wikitext(WIKI_URL)
    print(f"📄 {len(wt):,} bytes", file=sys.stderr)

    mbg_start = wt.find("==== Makan Bergizi Gratis ====")
    if mbg_start < 0:
        print("ERROR: MBG section not found", file=sys.stderr)
        sys.exit(1)

    cases = extract_mbg_table(wt[mbg_start:])
    stats = compute_stats(cases)

    data = {
        "metadata": {
            "title": "Kasus keracunan massal program Makan Bergizi Gratis",
            "source": "https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "license": "CC-BY-SA 3.0 (via Wikipedia)",
            "stats": stats,
        },
        "cases": cases,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ {OUTPUT_FILE}", file=sys.stderr)
    print(f"   {stats['total_incidents']} incidents, {stats['provinces_affected']} provinces", file=sys.stderr)
    print(json.dumps({"status": "ok", "output": str(OUTPUT_FILE), **stats}))


if __name__ == "__main__":
    main()
