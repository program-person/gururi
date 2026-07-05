"""transit.ls8h.com API の駅IDと graph.json の駅IDの対応表を生成する。

大回りルートの各区間（路線単位）を transit API の /plan で実ダイヤ照会するため、
「路線ID × 駅ID → transit API 駅ID」のマッピングを作る。

使い方:
    python scripts/build_transit_station_map.py          # 差分確認（dry-run）
    python scripts/build_transit_station_map.py --write  # backend/data/transit_station_map.json を更新

注意: サジェストAPIを駅名ごとに1回叩く（キャッシュあり・約300リクエスト）。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.transit.ls8h.com/api/v1"
UA = {"User-Agent": "omawari-app map builder (personal project)"}
ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "backend" / "data" / "graph.json"
OUT_PATH = ROOT / "backend" / "data" / "transit_station_map.json"

# 路線ID → transit API のフィードID（2026-07 時点の調査結果）
# 空リスト = transit API 未収録（奈良線・関西空港線）。
# H は学研都市線のみ収録で、JR東西線区間（北新地〜御幣島など）は未収録。
LINE_FEEDS: dict[str, list[str]] = {
    "O": ["jrwest-osaka-loop"],
    "A": ["jrwest-tokaido", "jrwest-hokuriku-main", "jrwest-sanyo-east"],
    "G": ["jrwest-fukuchiyama"],
    "H": ["jrwest-katamachi"],
    "Q": ["jrwest-yamatoji"],
    "F": ["jrwest-osaka-higashi"],
    "R": ["jrwest-hanwa"],
    "D": [],
    "B": ["jrwest-kosei"],
    "C": ["jrwest-kusatsu"],
    "V": ["jrwest-kansai-kamo-kameyama"],
    "E": ["jrwest-sanin-east"],
    "U": ["jrwest-sakurai"],
    "T": ["jrwest-wakayama"],
    "S": [],
    "HA": ["jrwest-hanwa-hagoromo"],
    "I": ["jrwest-kakogawa"],
}

# 同名駅の誤マッチ防止: グラフ座標との距離上限（km）
MAX_DIST_KM = 2.0

_suggest_cache: dict[str, list[dict]] = {}


def norm_name(name: str) -> str:
    """「ヶ/ケ」などの表記ゆれを吸収して比較する"""
    return name.replace("ヶ", "ケ")


def suggest(name: str) -> list[dict]:
    if name in _suggest_cache:
        return _suggest_cache[name]
    qs = urllib.parse.urlencode({"q": name})
    req = urllib.request.Request(f"{BASE}/locations/suggest?{qs}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    stations = data.get("stations", [])
    _suggest_cache[name] = stations
    time.sleep(0.1)  # 個人運営APIへの配慮
    return stations


def dist_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dy = (lat1 - lat2) * 111.0
    dx = (lng1 - lng2) * 111.0 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    stations = {s["id"]: s for s in graph["stations"]}

    # 路線ごとの駅ID集合（エッジ両端から抽出）
    line_stations: dict[str, set[str]] = {}
    for e in graph["edges"]:
        line_stations.setdefault(e["lineId"], set()).update(
            (e["fromStationId"], e["toStationId"])
        )

    result: dict[str, dict[str, str]] = {}
    missing: list[str] = []

    for line_id in sorted(line_stations):
        feeds = LINE_FEEDS.get(line_id)
        if feeds is None:
            print(f"[WARN] LINE_FEEDS 未定義の路線ID: {line_id}", file=sys.stderr)
            continue
        if not feeds:
            print(f"[SKIP] {line_id}: transit API 未収録")
            continue
        mapped: dict[str, str] = {}
        for sid in sorted(line_stations[line_id]):
            st = stations[sid]
            name, lat, lng = st["name"], st.get("lat"), st.get("lng")
            # 「ヶ/ケ」の表記ゆれで検索自体が空振りすることがあるため両方試す
            cands = list(suggest(name))
            for alt in (name.replace("ヶ", "ケ"), name.replace("ケ", "ヶ")):
                if alt != name:
                    cands += suggest(alt)
            found = None
            for cand in cands:
                if cand.get("feedId") not in feeds:
                    continue
                if norm_name(cand.get("name", "")) != norm_name(name):
                    continue
                if lat is not None and lng is not None:
                    clat, clng = cand.get("lat"), cand.get("lon")
                    if clat is not None and dist_km(lat, lng, clat, clng) > MAX_DIST_KM:
                        continue
                found = cand["id"]
                break
            if found:
                mapped[sid] = found
            else:
                missing.append(f"{line_id}:{sid}({name})")
        result[line_id] = mapped
        print(f"[OK] {line_id}: {len(mapped)}/{len(line_stations[line_id])} 駅をマッピング")

    if missing:
        print(f"\n[MISSING] {len(missing)} 件:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)

    if args.write:
        out = {
            "meta": {
                "source": BASE,
                "note": "路線ID -> 駅ID -> transit API 駅ID。build_transit_station_map.py で生成（手編集しない）",
            },
            "map": result,
        }
        OUT_PATH.write_text(
            json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"\n書き込み完了: {OUT_PATH}")
    else:
        print("\n(dry-run: --write で保存)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
