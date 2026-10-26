#!/usr/bin/env python3
"""Update the embedded listings snapshot in index.html from the live API.

This is the GitHub Actions timer for Shielded Skies. It does NOT make the
game truly live per page open: the browser still cannot fetch the API
directly (no CORS header), so the game falls back to this snapshot.
This script keeps that snapshot fresh on a schedule instead.

Safety: if the API fetch fails, the JSON is invalid, or the parsed pool
looks wrong, the script exits non-zero and changes NOTHING, so a bad
run never commits a broken index.html.

Usage: python3 scripts/update_listings.py [path/to/index.html]
Default path is index.html next to the repo root (workflow runs from root,
so pass index.html explicitly there).
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    TZ = timezone.utc

API_URL = "https://shielded-api.ord-dropz.xyz/api/shielded/listings"
GHOST_IDS = {1612, 1613, 2816, 2817, 2881, 2889}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Shielded-Skies-Snapshot-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise SystemExit(f"API HTTP {resp.status}")
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict):
        arr = data.get("listings") or data.get("data") or data.get("items") or []
    elif isinstance(data, list):
        arr = data
    else:
        raise SystemExit("API JSON is not a list/object")

    pool = {}
    for it in arr:
        if not isinstance(it, dict):
            continue
        raw_id = it.get("assetId", it.get("id", it.get("tokenId", it.get("pieceId"))))
        try:
            pid = int(raw_id)
            price = int(float(it.get("price")))
        except Exception:
            continue
        if pid < 0 or pid > 3332 or pid in GHOST_IDS or price <= 0:
            continue
        pool[pid] = price

    # Sanity guard: a healthy pool is dozens to low hundreds of items.
    if len(pool) < 10 or len(pool) > 1000:
        raise SystemExit(f"parsed pool size looks wrong: {len(pool)}")

    # PRICE_MAP: descending by price, tie-break by id ascending (matches game logic).
    ordered_desc = sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))
    price_map = ",".join(f"{pid}:{price}" for pid, price in ordered_desc)

    # BOSS_IDS: top 6 by price, then ascending for play order (cheapest first, finale most expensive).
    top6_desc = ordered_desc[:6]
    boss_ids = sorted(top6_desc, key=lambda kv: (kv[1], kv[0]))
    boss_str = ", ".join(str(pid) for pid, _ in boss_ids)
    top_id, top_price = boss_ids[-1]

    with open(path, encoding="utf-8") as f:
        txt = f.read()

    orig = txt
    new_price, n1 = re.subn(r"var PRICE_MAP = \{[^}]+\}", f"var PRICE_MAP = {{{price_map}}}", txt)
    if n1 != 1:
        raise SystemExit("PRICE_MAP pattern not found exactly once")
    txt = new_price
    new_boss, n2 = re.subn(r"var BOSS_IDS = \[[^\]]+\]", f"var BOSS_IDS = [{boss_str}]", txt)
    if n2 != 1:
        raise SystemExit("BOSS_IDS pattern not found exactly once")
    txt = new_boss

    # Snapshot date (Beijing date, matches the player-visible label).
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    txt = re.sub(r"构建时快照 \d{4}-\d{2}-\d{2}", f"构建时快照 {date_str}", txt)
    txt = re.sub(
        r'T\("构建时快照", "snapshot"\)',
        f'T("构建时快照 {date_str}", "snapshot {date_str}")',
        txt,
    )
    txt = re.sub(r"仅在售的 \d+ 件", f"仅在售的 {len(pool)} 件", txt)
    txt = re.sub(r'class="listing-count">\d+</span>', f'class="listing-count">{len(pool)}</span>', txt)
    # Boss hint in the side panel: keep the finale id/price honest.
    if top_price % 100000000 == 0:
        top_btc = f"{top_price // 100000000} BTC"
    else:
        top_btc = f"{top_price / 100000000:g} BTC"
    txt = re.sub(r"压轴是挂牌 [^ ]+ 的 #\d+", f"压轴是挂牌 {top_btc} 的 #{top_id}", txt)

    if txt == orig:
        print(f"no change (still {len(pool)} items)")
        return 0
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"updated: {len(pool)} items, BOSS_IDS=[{boss_str}], snapshot={date_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
