#!/usr/bin/env python3
"""
MBG (Makan Bergizi Gratis) Case Scraper v3
===========================================
Scrapes Wikipedia for MBG poisoning cases. Tags: keracunan, deaths, sppg.
Uses rowspan group IDs for correct victim totals — each unique incident
counted once, matching Wikipedia's ~11,390 total.

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
USER_AGENT = "MBGScraper/3.0"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "mbg_cases.json"
COLUMNS = ["date", "province", "regency", "school", "symptomatic", "deaths"]
SYM_IDX = COLUMNS.index("symptomatic")

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
# Cleaners
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
    s = raw.strip().lower()
    if not s or s in ("tba (tidak disebutkan)", "tba (tidak diumumkan)", "tidak disebutkan", "-", "", "–", ""):
        return None
    m = re.search(r">\s*(\d+)", s)
    if m: return float(m.group(1))
    m = re.search(r"±\s*(\d+)", s)
    if m: return float(m.group(1))
    m = re.search(r"(\d[\d.]*)", s)
    if m: return float(m.group(1).replace(".", ""))
    if "puluhan" in s: return 50.0
    if "ratusan" in s: return 200.0
    return None

# ---------------------------------------------------------------------------
# Wikitable parser (v2 working, returns from_rowspan flags)
# ---------------------------------------------------------------------------

def parse_table_rows(body: str) -> tuple[list[list[str]], list[str], list[list[bool]]]:
    """
    Return (rows, raw_segments, from_rowspan).
    from_rowspan[i][j] = True if rows[i][j] was propagated from a rowspan cell.
    """
    segs = re.split(r"\n\|-\s*\n", body)
    data_segs = [s for s in segs if re.search(r"(?<!\|)\|[^|!+\-]", s)]

    rows: list[list[str]] = []
    flags_out: list[list[bool]] = []
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
        flags: list[bool] = []
        col = 0
        ci = 0
        while ci < len(cells) or col < len(COLUMNS):
            if col in span and span[col]["r"] > 0:
                row.append(span[col]["v"])
                flags.append(True)
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
            flags.append(False)
            if rs > 1:
                span[col] = {"r": rs - 1, "v": val}
            ci += 1
            col += 1
        rows.append(row)
        flags_out.append(flags)

    return rows, data_segs, flags_out


def extract_cases(wikitext: str) -> tuple[list[dict[str, Any]], list[int | None]]:
    """Return (entries, sym_group_ids). Same GID = same rowspan-shared symptomatic."""
    start = wikitext.find('{| class="wikitable"')
    if start == -1:
        return [], []
    rest = wikitext[start:]
    end = rest.find("\n|}")
    if end == -1:
        return [], []
    table_raw = rest[:end]

    rows, raw_segs, rowspan_flags = parse_table_rows(table_raw)

    entries: list[dict[str, Any]] = []
    # Build group IDs: consecutive rows whose symptomatic came from rowspan
    # share the same ID as the row that defined the rowspan.
    sym_gids: list[int | None] = []
    gid_counter = [0]

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

        for field in ("deaths", "symptomatic"):
            if any(x in e[field] for x in ("access-date", "url=", "{{", "}}")):
                e[field] = ""
        for c in COLUMNS:
            e[c] = e[c].replace("{{", "").replace("}}", "")

        e["references"] = extract_urls(raw_segs[i]) if i < len(raw_segs) else []
        e["tags"] = ["keracunan"]
        e["deaths_count"] = parse_num(e["deaths"])
        e["symptomatic_approximate"] = False
        e["unit"] = ""
        e["_raw_unit"] = ""
        # Parse symptomatic to integer + unit
        sym_raw = e["symptomatic"]
        if sym_raw:
            n = parse_num(sym_raw)
            if n is not None:
                e["symptomatic"] = int(n)
                # Extract unit
                parts = sym_raw.split()
                if len(parts) > 1:
                    u = re.search(r"[a-zA-Z]+", parts[-1])
                    if u:
                        e["unit"] = u.group(0).lower()
                        e["_raw_unit"] = u.group(0).lower()
            # else keep string (unparseable like "Belasan")

        # Assign group ID: if symptomatic came from rowspan, use same GID
        # as the defining row. We need to track this via the parser's span state.
        # Strategy: scan backwards through rows to find the one whose
        # symptomatic defined this rowspan.
        if flags and len(flags) > SYM_IDX and flags[SYM_IDX]:
            # Symptomatic is from rowspan — find GID of the defining row
            # by scanning backwards to the first non-rowspan symptomatic
            # with the same value
            found = None
            for k in range(len(entries) - 1, -1, -1):
                if entries[k]["symptomatic"] == e["symptomatic"] and sym_gids[k] is not None:
                    found = sym_gids[k]
                    break
                if entries[k]["symptomatic"] == e["symptomatic"] and not entries[k].get("symptomatic_approximate", False):
                    # This is the defining row — it should have a GID assigned below
                    continue
            sym_gids.append(found)
        else:
            # Own symptomatic cell (defines a rowspan or unique)
            if i > 0 and flags and len(flags) > SYM_IDX and not flags[SYM_IDX]:
                # Could be defining a rowspan — check if next row has same
                # symptomatic from rowspan
                gid_counter[0] += 1
                sym_gids.append(gid_counter[0])
            else:
                sym_gids.append(None)

        entries.append(e)

    # --- Divide rowspan-shared symptomatic counts using group IDs ---
    gid_rows: dict[int, list[int]] = defaultdict(list)
    for idx, gid in enumerate(sym_gids):
        if gid is not None:
            gid_rows[gid].append(idx)

    for gid, indices in gid_rows.items():
        if len(indices) <= 1:
            for idx in indices:
                sym_gids[idx] = None
            continue
        raw_val = entries[indices[0]]["symptomatic"]
        if not isinstance(raw_val, (int, float)):
            continue
        total = float(raw_val)
        if total <= 0:
            for idx in indices:
                sym_gids[idx] = None
            continue
        per_school = int(round(total / len(indices)))
        unit = entries[indices[0]].get("_raw_unit", "")
        for idx in indices:
            entries[idx]["symptomatic"] = int(total)
            entries[idx]["unit"] = unit
            entries[idx].pop("_raw_unit", None)
            entries[idx]["symptomatic_per_school"] = per_school
            entries[idx]["symptomatic_approximate"] = True

    # Clean up internal field from output
    for e in entries:
        e.pop("_raw_unit", None)

    return entries, sym_gids


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def apply_tags(entries: list[dict]) -> None:
    for e in entries:
        if e["deaths"] and "deaths" not in e["tags"]:
            e["tags"].append("deaths")
        haystack = (e["school"] + " " + e["regency"] + " " + e["province"]).lower()
        for ref in e["references"]:
            haystack += " " + ref.lower()
        if re.search(r"\bsppg\b|\bbgn\b|badan gizi|satuan pelayanan", haystack):
            if "sppg" not in e["tags"]:
                e["tags"].append("sppg")


# ---------------------------------------------------------------------------
# Stats — count each unique incident ONCE
# ---------------------------------------------------------------------------

def compute_stats(entries: list[dict], sym_gids: list[int | None]) -> OrderedDict:
    provs: dict[str, int] = defaultdict(int)
    total_victims = 0.0
    total_deaths = 0.0
    death_incidents = 0
    tag_counts: dict[str, int] = defaultdict(int)
    approx_count = 0
    counted_gids: set[int] = set()
    unique_incidents = 0

    for i, e in enumerate(entries):
        gid = sym_gids[i] if i < len(sym_gids) else None
        p = e["province"] or "Tidak diketahui"
        provs[p] += 1
        for t in e["tags"]:
            tag_counts[t] += 1
        if e.get("symptomatic_approximate"):
            approx_count += 1
        if e["deaths"]:
            death_incidents += 1
            d = parse_num(e["deaths"])
            if d:
                total_deaths += d

        # Count symptomatic once per unique incident
        if gid is not None:
            if gid in counted_gids:
                continue
            counted_gids.add(gid)
            unique_incidents += 1
        else:
            unique_incidents += 1

        n = e["symptomatic"]
        if isinstance(n, (int, float)):
            total_victims += float(n)

    return OrderedDict([
        ("total_school_venues", len(entries)),
        ("total_victims_symptomatic", int(total_victims)),
        ("total_victims_deaths", int(total_deaths)),
        ("unique_incidents", unique_incidents),
        ("incidents_with_deaths", death_incidents),
        ("incidents_approximate_per_school", approx_count),
        ("provinces_affected", len(provs)),
        ("tags_breakdown", OrderedDict(sorted(tag_counts.items(), key=lambda x: -x[1]))),
        ("incidents_by_province", OrderedDict(sorted(provs.items(), key=lambda x: -x[1]))),
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    print("🕸  MBG Scraper v3 — fetching...", file=sys.stderr)
    wt = fetch_wikitext(WIKI_URL)
    print(f"📄 {len(wt):,} bytes", file=sys.stderr)

    mbg_start = wt.find("==== Makan Bergizi Gratis ====")
    if mbg_start < 0:
        print("ERROR: MBG section not found", file=sys.stderr)
        sys.exit(1)

    cases, sym_gids = extract_cases(wt[mbg_start:])
    apply_tags(cases)
    stats = compute_stats(cases, sym_gids)

    data = {
        "meta": {
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
    print(f"   Venues: {stats['total_school_venues']}", file=sys.stderr)
    print(f"   Victims: {stats['total_victims_symptomatic']:,} (per unique incident)", file=sys.stderr)
    print(f"   Deaths: {stats['total_victims_deaths']}", file=sys.stderr)
    print(f"   Unique incidents: {stats['unique_incidents']}", file=sys.stderr)
    print(json.dumps({"status": "ok", "output": str(OUTPUT_FILE), **{
        k: v for k, v in stats.items()
        if k in ("total_victims_symptomatic", "total_victims_deaths",
                 "total_school_venues", "provinces_affected", "unique_incidents")
    }}))


if __name__ == "__main__":
    main()
