#!/usr/bin/env python3
"""
MBG (Makan Bergizi Gratis) Case Scraper
========================================
Scrapes Wikipedia for mass food-poisoning incidents from Indonesia's
Makan Bergizi Gratis program. Outputs clean JSON with:
- Tags: keracunan, deaths, sppg
- Approximate flag for rowspan-divided counts
- Accurate victim totals (no rowspan double-counting)

Source: https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis
"""

import json
import re
import subprocess
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WIKI_URL = (
    "https://id.wikipedia.org/w/index.php?title="
    "Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis&action=raw"
)
USER_AGENT = "MBGScraper/2.0"
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
    text = re.sub(r"{{[^}]*}}", "", text)
    text = text.replace("[[", "").replace("]]", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"'}\[\]\\,;|]+", text)

def parse_num(raw: str) -> float | None:
    """Parse a symptomatic-count string to approximate number."""
    s = raw.strip().lower()
    if not s or s in ("tba (tidak disebutkan)", "tba (tidak diumumkan)", "tidak disebutkan", "-", "", "–"):
        return None
    # ">100 Siswa" → 100
    m = re.search(r">\s*(\d+)", s)
    if m:
        return float(m.group(1))
    # "± 30 Siswa" → 30
    m = re.search(r"±\s*(\d+)", s)
    if m:
        return float(m.group(1))
    # "1.333 Siswa" → 1333
    m = re.search(r"(\d[\d.]*)", s)
    if m:
        return float(m.group(1).replace(".", ""))
    # "Puluhan" → 50
    if "puluhan" in s:
        return 50.0
    # "Ratusan" → 200
    if "ratusan" in s:
        return 200.0
    return None

# ---------------------------------------------------------------------------
# Rowspan-aware wikitable parser with rowspan tracking
# ---------------------------------------------------------------------------

def parse_table_rows(body: str) -> tuple[list[list[str]], list[str], list[list[bool]]]:
    """
    Return (rows, raw_segments, from_rowspan).
    from_rowspan[i][j] = True if rows[i][j] was propagated from a rowspan.
    """
    segs = re.split(r"\n\|-\s*\n", body)
    data_segs = [s for s in segs if re.search(r"(?<!\|)\|[^|!+\-]", s)]

    rows: list[list[str]] = []
    rowspan_flags: list[list[bool]] = []
    span: dict[int, dict] = {}  # col -> {"r": remaining, "v": value}

    for seg in data_segs:
        cells = []
        for line in seg.split("\n"):
            line = line.strip()
            if not line.startswith("|") or line.startswith("|-|+|!") or line.startswith("|!"):
                continue
            cell = re.sub(r"^\|+", "", line).strip()
            cells.append(cell)

        row: list[str] = []
        flags: list[bool] = []
        col = 0
        ci = 0
        while ci < len(cells) or col < len(COLUMNS):
            if col in span and span[col]["r"] > 0:
                row.append(span[col]["v"])
                flags.append(True)  # from rowspan
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
            flags.append(False)  # own cell, not from rowspan
            if rs > 1:
                span[col] = {"r": rs - 1, "v": val}
            ci += 1
            col += 1
        rows.append(row)
        rowspan_flags.append(flags)

    return rows, data_segs, rowspan_flags


def extract_mbg_table(wikitext: str) -> list[dict]:
    start = wikitext.find('{| class="wikitable"')
    if start == -1:
        return []
    rest = wikitext[start:]
    end = rest.find("\n|}")
    if end == -1:
        return []
    table_raw = rest[:end]

    rows, raw_segs, rowspan_flags = parse_table_rows(table_raw)
    entries: list[dict[str, Any]] = []
    entries_rowspan_flags: list[list[bool]] = []

    for i, row in enumerate(rows):
        e: dict[str, Any] = {}
        for j, col in enumerate(COLUMNS):
            e[col] = row[j] if j < len(row) else ""
        flags = rowspan_flags[i] if i < len(rowspan_flags) else []

        # Filter junk rows
        if e["date"].startswith("Tanggal") or e["province"].startswith("Provinsi"):
            continue
        if e["date"] in ("+", "TOTAL"):
            continue
        if all(not e[c] for c in COLUMNS):
            continue

        # Clean reference artifacts from numeric fields
        for field in ("deaths", "symptomatic"):
            if any(x in e[field] for x in ("access-date", "url=", "{{", "}}")):
                e[field] = ""
        for c in COLUMNS:
            e[c] = e[c].replace("{{", "").replace("}}", "")

        e["references"] = extract_urls(raw_segs[i]) if i < len(raw_segs) else []
        e["tags"] = ["keracunan"]
        e["deaths_count"] = parse_num(e["deaths"])
        e["symptomatic_approximate"] = False

        entries.append(e)
        entries_rowspan_flags.append(flags)

    # --- Post-process: handle rowspan-shared symptomatic counts ---
    sym_idx = COLUMNS.index("symptomatic")
    i = 0
    while i < len(entries):
        e = entries[i]
        flags_i = entries_rowspan_flags[i] if i < len(entries_rowspan_flags) else []

        if not e["symptomatic"] or not e["date"]:
            i += 1
            continue

        # If this row's symptomatic is NOT from rowspan (it's its own cell),
        # it could still be the first row of a rowspan group.
        # We need to check if it DEFINES a rowspan for symptomatic.
        # If it does, the next row(s) will have it from rowspan → skip this.
        if len(flags_i) > sym_idx and not flags_i[sym_idx]:
            i += 1
            continue

        # Symptomatic came from rowspan → find full group & divide
        group_start = i
        while group_start > 0:
            prev = entries[group_start - 1]
            if prev["date"] == e["date"] and prev["symptomatic"] == e["symptomatic"]:
                group_start -= 1
            else:
                break

        group_end = i
        while group_end < len(entries) - 1:
            nxt = entries[group_end + 1]
            if nxt["date"] == e["date"] and nxt["symptomatic"] == e["symptomatic"]:
                group_end += 1
            else:
                break

        group_size = group_end - group_start + 1
        if group_size <= 1:
            i += 1
            continue

        raw_val = e["symptomatic"]
        total_num = parse_num(raw_val)
        if total_num is None:
            i = group_end + 1
            continue

        per_school = round(total_num / group_size, 1)
        parts = raw_val.split()
        unit = parts[-1] if len(parts) > 1 else ""

        for j in range(group_start, group_end + 1):
            entries[j]["symptomatic"] = f"{per_school:.1f} {unit}" if unit else f"{per_school:.1f}"
            entries[j]["symptomatic_approximate"] = True

        i = group_end + 1

    return entries


# ---------------------------------------------------------------------------
# Tags enrichment
# ---------------------------------------------------------------------------

def apply_tags(entries: list[dict]) -> None:
    """Add secondary tags based on data."""
    for e in entries:
        # deaths tag
        if e["deaths"]:
            if "deaths" not in e["tags"]:
                e["tags"].append("deaths")

        # sppg tag: check if reference URLs/titles mention SPPG or BGN
        # Also check the school/region name
        haystack = (e["school"] + " " + e["regency"] + " " + e["province"]).lower()
        for ref in e["references"]:
            haystack += " " + ref.lower()
        if re.search(r"\bsppg\b|\bbgn\b|badan gizi|satuan pelayanan", haystack):
            if "sppg" not in e["tags"]:
                e["tags"].append("sppg")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def compute_stats(entries: list[dict]) -> OrderedDict:
    provs = defaultdict(int)
    death_incidents = 0
    total_symptomatic = 0.0
    total_deaths = 0.0
    tag_counts: dict[str, int] = defaultdict(int)
    approximate_count = 0

    for e in entries:
        p = e["province"] or "Tidak diketahui"
        provs[p] += 1
        if e["deaths"]:
            death_incidents += 1
            d = parse_num(e["deaths"])
            if d:
                total_deaths += d
        sym = parse_num(e["symptomatic"])
        if sym:
            total_symptomatic += sym
        for t in e["tags"]:
            tag_counts[t] += 1
        if e.get("symptomatic_approximate"):
            approximate_count += 1

    return OrderedDict([
        ("total_school_venues", len(entries)),
        ("total_victims_symptomatic", int(total_symptomatic)),
        ("total_victims_deaths", int(total_deaths)),
        ("incidents_with_deaths", death_incidents),
        ("incidents_approximate_count", approximate_count),
        ("provinces_affected", len(provs)),
        ("tags_breakdown", OrderedDict(sorted(tag_counts.items(), key=lambda x: -x[1]))),
        ("incidents_by_province", OrderedDict(sorted(provs.items(), key=lambda x: -x[1]))),
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    print("🕸  MBG Scraper v2 — fetching...", file=sys.stderr)
    wt = fetch_wikitext(WIKI_URL)
    print(f"📄 {len(wt):,} bytes", file=sys.stderr)

    mbg_start = wt.find("==== Makan Bergizi Gratis ====")
    if mbg_start < 0:
        print("ERROR: MBG section not found", file=sys.stderr)
        sys.exit(1)

    cases = extract_mbg_table(wt[mbg_start:])
    apply_tags(cases)
    stats = compute_stats(cases)

    data = {
        "tscraped_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "title": "Kasus keracunan massal program Makan Bergizi Gratis",
            "source": "https://id.wikipedia.org/wiki/Daftar_kasus_keracunan_massal_program_Makan_Bergizi_Gratis",
            "license": "CC-BY-SA 3.0 (via Wikipedia)",
            "stats": stats,
        },
        "cases": cases,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ {OUTPUT_FILE}", file=sys.stderr)
    print(f"   Venues: {stats['total_school_venues']}", file=sys.stderr)
    print(f"   Victims (symptomatic): {stats['total_victims_symptomatic']:,}", file=sys.stderr)
    print(f"   Deaths: {stats['total_victims_deaths']}", file=sys.stderr)
    print(f"   Tags: {dict(stats['tags_breakdown'])}", file=sys.stderr)
    print(json.dumps({
        "status": "ok",
        "output": str(OUTPUT_FILE),
        "total_victims_symptomatic": stats["total_victims_symptomatic"],
        "total_victims_deaths": stats["total_victims_deaths"],
        "total_school_venues": stats["total_school_venues"],
        "provinces_affected": stats["provinces_affected"],
    }))


if __name__ == "__main__":
    main()
