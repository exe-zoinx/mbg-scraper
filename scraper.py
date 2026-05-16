#!/usr/bin/env python3
"""
MBG (Makan Bergizi Gratis) Poisoning Cases Scraper
==================================================
Scrapes Wikipedia for mass food-poisoning data related to
free school meal programs. Outputs clean JSON.

Source: https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WIKI_URL = (
    "https://id.wikipedia.org/w/index.php?title="
    "Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis&action=raw"
)
USER_AGENT = "MBGScraper/1.0 (github:exe-zoinx/mbg-scraper)"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "mbg_cases.json"

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_wikitext(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A", USER_AGENT, url],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        result = subprocess.run(
            ["wget", "-qO-", "--timeout=25", url],
            capture_output=True, text=True,
        )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Failed to fetch: {result.stderr[:500]}")
    return result.stdout

# ---------------------------------------------------------------------------
# Wikitext helpers
# ---------------------------------------------------------------------------

def strip_refs(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/>", "", text)
    return text.strip()

def strip_wiki_links(text: str) -> str:
    text = re.sub(r"\[\[([^|\]]+)\|([^]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
    return text.strip()

def clean_val(text: str) -> str:
    text = strip_refs(text)
    text = strip_wiki_links(text)
    # Remove HTML tags
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = text.replace("\u00a0", " ")
    # Clean template remnants like {{...}}
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # Clean stray [[, ]] brackets
    text = text.replace("[[", "").replace("]]", "")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def parse_rowspan(text: str) -> int:
    m = re.search(r'rowspan\s*=\s*["\']?(\d+)', text)
    return int(m.group(1)) if m else 1

def extract_ref_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"'}\]\[,;|]+", text)

# ---------------------------------------------------------------------------
# Section parsers (bullet lists)
# ---------------------------------------------------------------------------

def parse_bullets(text: str, source: str) -> list[dict]:
    entries = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("*"):
            continue
        bullet = line.lstrip("* ").strip()
        if not bullet:
            continue
        desc = clean_val(bullet)
        refs = extract_ref_urls(bullet)
        date_m = re.search(
            r"(\d{1,2}\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+\d{4})"
            r"|((?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+\d{4})",
            desc,
        )
        entries.append({
            "date": (date_m.group(1) or date_m.group(2)) if date_m else None,
            "description": desc,
            "references": refs,
            "source": source,
        })
    return entries

# ---------------------------------------------------------------------------
# Wikitable row parser (rowspan-aware)
# ---------------------------------------------------------------------------

COLUMNS = ["date", "province", "regency", "school", "symptomatic", "deaths"]

def parse_table_rows(table_body: str) -> list[list[str]]:
    """
    Take the wikitable body (between {| and |}) and produce a list of rows,
    each row being a list of cell values with rowspan resolved.
    
    Wiki table syntax used in this page:
      - Each row starts after a |- line
      - Each cell starts with | on its own line:
          | cell content
          | attribute | cell content  
      - || may separate cells on the same line
      - rowspan="N" means the cell spans N rows
    """
    # Split into row segments
    row_segs = re.split(r"\n\|-\s*\n", table_body)
    
    # Skip caption/header — find first row with pipe-after-pipe (data)
    # The header has ! (header cells), the data has | (normal cells)
    data_segs = []
    for seg in row_segs:
        # Check if this row has a data cell (| not followed by - or + or !)
        if re.search(r"(?<!\|)\|[^|!+\-]", seg):
            data_segs.append(seg)
    
    if not data_segs:
        return []

    rows: list[list[str]] = []
    # rowspan active: dict[col_index] = {"remaining": int, "value": str}
    span: dict[int, dict] = {}

    for seg in data_segs:
        cells = _extract_cells(seg)
        row: list[str] = []
        col = 0
        cell_idx = 0

        while cell_idx < len(cells) or col < len(COLUMNS):
            # If we have a pending rowspan at this column, emit it
            if col in span and span[col]["remaining"] > 0:
                row.append(span[col]["value"])
                span[col]["remaining"] -= 1
                if span[col]["remaining"] <= 0:
                    del span[col]
                col += 1
                continue

            if cell_idx >= len(cells):
                break

            raw = cells[cell_idx]
            rs = parse_rowspan(raw)
            # Remove rowspan attr and leading pipes
            val_raw = re.sub(r"^[\|]+", "", raw)
            val_raw = re.sub(r"\s*rowspan\s*=\s*[\"']?\d+[\"']?\s*", "", val_raw)
            # If there's a pipe within (attribute|content), take the part after last pipe
            val_raw = val_raw.rsplit("|", 1)[-1] if "|" in val_raw else val_raw
            val = clean_val(val_raw)

            row.append(val)
            if rs > 1:
                span[col] = {"remaining": rs - 1, "value": val}
            cell_idx += 1
            col += 1

        rows.append(row)

    return rows


def _extract_cells(row_text: str) -> list[str]:
    """Extract individual cell wikitext from a row segment."""
    cells = []
    # Split by lines, find lines starting with | (not |- and not |+ and not !!)
    lines = row_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        if line.startswith("|-"):
            continue
        if line.startswith("|+"):
            continue
        if line.startswith("|!"):
            # header-style |! is also a cell marker in some wikitext
            # But in our table, data rows use | not !
            continue
        
        # Remove leading | or ||
        cell = re.sub(r"^\|+", "", line)
        if cell.strip():
            cells.append(cell)
    
    return cells


# ---------------------------------------------------------------------------
# Main table extraction
# ---------------------------------------------------------------------------

def extract_mbg_table(wikitext: str) -> list[dict]:
    """Find the MBG wikitable, extract rows with rowspan, return structured entries."""
    # Locate the table
    start = wikitext.find('{| class="wikitable"')
    if start == -1:
        # Try alternate syntax
        start = wikitext.find('{|')
        if start == -1:
            return []
    
    rest = wikitext[start:]
    # Find closing |}
    end = rest.find("\n|}")
    if end == -1:
        end = rest.find("\n|}")
    if end == -1:
        return []
    
    table_raw = rest[:end]
    
    # Also get raw row segments for reference extraction
    row_segs_raw = re.split(r"\n\|-\s*\n", table_raw)
    
    rows_raw = parse_table_rows(table_raw)
    
    entries = []
    for row_idx, row in enumerate(rows_raw):
        entry = {}
        for i, col_name in enumerate(COLUMNS):
            if i < len(row):
                entry[col_name] = row[i]
            else:
                entry[col_name] = ""
        
        # Skip header-like rows and empty rows
        if entry.get("date", "").startswith("Tanggal") or entry.get("province", "").startswith("Provinsi"):
            continue
        
        vals = [entry[c] for c in COLUMNS]
        if all(v == "" for v in vals):
            continue
        
        # Clean deaths field — remove reference artifacts
        if "access-date" in entry["deaths"] or "url=" in entry["deaths"] or "{{" in entry["deaths"] or "}}" in entry["deaths"]:
            entry["deaths"] = ""
        
        # Clean symptomatic field the same way
        if "access-date" in entry["symptomatic"] or "{{" in entry["symptomatic"] or "}}" in entry["symptomatic"]:
            entry["symptomatic"] = ""
        
        # Clean any remaining {{, }} artifacts in all fields
        for k in COLUMNS:
            entry[k] = entry[k].replace("{{", "").replace("}}", "")
        
        # Extract references from raw segment if available
        refs = []
        if row_idx < len(row_segs_raw):
            refs = extract_ref_urls(row_segs_raw[row_idx])
        entry["references"] = refs
        
        entries.append(entry)
    
    return entries


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def parse_china_text(text: str) -> list[dict]:
    """Parse a single paragraph from the Tiongkok section."""
    text = text.strip()
    if not text:
        return []
    desc = clean_val(text)
    if not desc:
        return []
    refs = re.findall(r"https?://[^\s<>\"'}\]\[,;|]+", text)
    return [{
        "date": None,
        "description": desc,
        "references": refs,
        "source": "Tiongkok — Free school meal program",
    }]


def compute_stats(data: dict) -> dict:
    mbg = data["cases"]["indonesia_mbg"]
    by_province = defaultdict(int)
    deaths_count = 0
    for c in mbg:
        prov = c["province"] or "Tidak diketahui"
        by_province[prov] += 1
        if c["deaths"] not in ("", "–", "-", "0"):
            deaths_count += 1
    return {
        "total_incidents": len(mbg),
        "provinces_affected": len(by_province),
        "incidents_by_province": dict(sorted(by_province.items(), key=lambda x: -x[1])),
        "incidents_with_deaths": deaths_count,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("🕸  MBG Scraper — fetching wikitext...", file=sys.stderr)
    wikitext = fetch_wikitext(WIKI_URL)
    print(f"📄 {len(wikitext):,} bytes", file=sys.stderr)

    # --- India ---
    india = []
    m = re.search(r"=== India ===(.*?)(?=\n\s*(?:={2,3}|$))", wikitext, re.DOTALL)
    if m:
        india = parse_bullets(m.group(1), "India — Midday Meal Scheme")

    # --- Indonesia MBG ---
    mbg_start = wikitext.find("==== Makan Bergizi Gratis ====")
    if mbg_start >= 0:
        mbg_section = wikitext[mbg_start:]
        mbg = extract_mbg_table(mbg_section)
    else:
        mbg = []

    # --- Korea Selatan ---
    korea = []
    m = re.search(r"=== Korea Selatan ===(.*?)(?=\n\s*(?:={2,3}|$))", wikitext, re.DOTALL)
    if m:
        korea = parse_bullets(m.group(1), "Korea Selatan — School meal program")

    # --- Tiongkok ---
    china = []
    m = re.search(r"===Tiongkok===(.*?)(?=\n\s*(?:={2,3}|$))", wikitext, re.DOTALL)
    if m:
        china = parse_china_text(m.group(1))

    data = {
        "metadata": {
            "title": "Daftar kasus keracunan massal program Makan Bergizi Gratis",
            "source_url": "https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(india) + len(mbg) + len(korea) + len(china),
            "data_license": "CC-BY-SA 3.0 (via Wikipedia)",
        },
        "cases": {
            "india": india,
            "indonesia_mbg": mbg,
            "korea_selatan": korea,
            "tiongkok": china,
        },
    }
    data["metadata"]["stats"] = compute_stats(data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    s = data["metadata"]["stats"]
    print(f"✅ {OUTPUT_FILE}", file=sys.stderr)
    print(f"   MBG: {s['total_incidents']} incidents / {s['provinces_affected']} provinces", file=sys.stderr)
    print(f"   India: {len(india)} | Korea: {len(korea)} | China: {len(china)}", file=sys.stderr)
    print(json.dumps({"status": "ok", "output": str(OUTPUT_FILE), **s}))


if __name__ == "__main__":
    main()
