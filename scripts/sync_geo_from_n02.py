#!/usr/bin/env python3
"""国土数値情報 N02 から駅座標・駅間キロを backend/generate_graph.py に同期する。

- 駅座標: N02_Station.geojson の駅ジオメトリ重心で COORDS を更新
- 駅間距離: N02_RailroadSection.geojson の線路ジオメトリに駅を射影し、
  線路沿い距離を 0.1km 単位で算出して seq() の distance を更新

Usage:
  python scripts/sync_geo_from_n02.py [--data-dir DIR] [--write]

  --write を付けない限り generate_graph.py は変更せず、差分レポートのみ表示。

Requirements:
  pip install shapely
"""

import argparse
import io
import json
import math
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    from shapely.geometry import shape, Point, LineString, MultiLineString
    from shapely.ops import linemerge, transform
except ImportError:
    print("ERROR: shapely が必要です: pip install shapely", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PY = ROOT / "backend" / "generate_graph.py"

JRW_OPERATOR = "西日本旅客鉄道"

# graph.json の路線ID → N02_003（路線名）候補
LINE_ID_TO_N02: dict[str, list[str]] = {
    "O":  ["大阪環状線"],
    "A":  ["東海道線", "山陽線", "北陸線"],
    "G":  ["福知山線"],
    "H":  ["JR東西線", "片町線"],
    "Q":  ["関西線", "大阪環状線"],
    "F":  ["おおさか東線", "片町線"],  # 鴫野〜放出は片町線の線路を走行
    "R":  ["阪和線"],
    "D":  ["奈良線"],
    "B":  ["湖西線"],
    "C":  ["草津線"],
    "V":  ["関西線"],
    "E":  ["山陰線"],
    "U":  ["桜井線"],
    "T":  ["和歌山線"],
    "S":  ["関西空港線"],
    "HA": ["阪和線"],
    "I":  ["加古川線"],
    "P":  ["桜島線"],  # JRゆめ咲線（N02上の正式名称は桜島線）
}

# 駅の N02 照合で JR西以外の運営者も許可する駅（共用駅対策）
ANY_OPERATOR_OK = {"りんくうタウン", "関西空港"}

# 駅名正規化テーブル（当アプリ表記 → N02表記）
NAME_ALIASES: dict[str, str] = {}

_FW2HW = str.maketrans(
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ０１２３４５６７８９",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
)


def norm(name: str) -> str:
    return name.translate(_FW2HW).replace("ヶ", "ケ").strip()


# 対象地域（近畿圏）の中心緯度。cos(lat) を点ごとに変えると
# 経度の絶対値(≈135)に緯度差が掛かって南北距離が大きく歪むため、必ず固定する。
REF_COS = math.cos(math.radians(34.85))


def to_km(geom):
    """経緯度ジオメトリを正距円筒近似（km単位）へ変換"""
    def f(lng, lat):
        return (lng * 111.32 * REF_COS, lat * 110.57)
    return transform(f, geom)


def geom_centroid_latlng(geom_dict: dict) -> tuple[float, float]:
    """MultiLineString/LineString の全頂点平均 (lat, lng)"""
    coords: list[tuple[float, float]] = []

    def walk(c):
        if isinstance(c[0], (int, float)):
            coords.append((c[0], c[1]))
        else:
            for x in c:
                walk(x)

    walk(geom_dict["coordinates"])
    lng = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return (round(lat, 5), round(lng, 5))


# ----------------------------------------------------------------
# generate_graph.py のパース
# ----------------------------------------------------------------
COORD_RE = re.compile(r'^(\s*)"([a-z]+)":\s*\(([\d.]+),\s*([\d.]+)\)(,?)(\s*#.*)?$')
ENTRY_RE = re.compile(r'^(\s*\("([a-z]+)",\s*"([^"]+)",\s*)([\d.]+)(,\s*\d+\),?.*)$')
SEQ_END_RE = re.compile(r'^\],\s*"([A-Z]+)"\)')


def parse_graph_py(text: str):
    """(coords行index一覧, seqブロック一覧) を返す。
    seqブロック: {"lid": str, "entries": [(行index, sid, name, dist)]}
    """
    lines = text.splitlines()
    coord_lines: dict[str, int] = {}
    blocks = []
    cur_entries = []
    in_seq = False
    for i, ln in enumerate(lines):
        m = COORD_RE.match(ln)
        if m:
            coord_lines[m.group(2)] = i
            continue
        if re.match(r"^(seq\(\[|LOOP = \[)", ln.strip()):
            in_seq = True
            cur_entries = []
            continue
        if in_seq:
            me = ENTRY_RE.match(ln)
            if me:
                cur_entries.append((i, me.group(2), me.group(3), float(me.group(4))))
                continue
            ms = SEQ_END_RE.match(ln.strip())
            if ms:
                blocks.append({"lid": ms.group(1), "entries": cur_entries})
                in_seq = False
                continue
            if ln.strip() == "]":  # LOOP リスト終端（seq(LOOP, "O") は後続）
                blocks.append({"lid": "O", "entries": cur_entries})
                in_seq = False
    return lines, coord_lines, blocks


# ----------------------------------------------------------------
# メイン
# ----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"C:\Users\hirom\dev\data\N02-20_GML")
    ap.add_argument("--write", action="store_true", help="generate_graph.py を書き換える")
    ap.add_argument("--max-snap-km", type=float, default=0.6,
                    help="駅→線路の射影を有効とみなす最大距離(km)")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)

    text = GRAPH_PY.read_text(encoding="utf-8")
    lines, coord_lines, blocks = parse_graph_py(text)

    # 駅ごとの (名称, 期待N02路線名集合, 現座標)
    station_names: dict[str, str] = {}
    station_n02_lines: dict[str, set[str]] = {}
    for b in blocks:
        for _, sid, name, _ in b["entries"]:
            station_names[sid] = name
            station_n02_lines.setdefault(sid, set()).update(LINE_ID_TO_N02[b["lid"]])

    cur_coords: dict[str, tuple[float, float]] = {}
    for sid, li in coord_lines.items():
        m = COORD_RE.match(lines[li])
        cur_coords[sid] = (float(m.group(3)), float(m.group(4)))

    # ---------------- 駅座標 ----------------
    st_data = json.loads((data_dir / "N02-20_Station.geojson").read_text(encoding="utf-8"))
    st_index: dict[str, list[dict]] = {}
    for f in st_data["features"]:
        p = f["properties"]
        st_index.setdefault(norm(p.get("N02_005") or ""), []).append(f)

    new_coords: dict[str, tuple[float, float]] = {}
    unmatched: list[str] = []
    for sid, name in station_names.items():
        key = norm(NAME_ALIASES.get(name, name))
        cands = st_index.get(key, [])
        jrw = [f for f in cands if JRW_OPERATOR in (f["properties"].get("N02_004") or "")]
        pool = jrw if (jrw or name not in ANY_OPERATOR_OK) else cands
        # 路線名で絞り込み（絞って0件になるなら名前一致のみで続行）
        line_hit = [f for f in pool if (f["properties"].get("N02_003") or "") in station_n02_lines[sid]]
        pool = line_hit or pool
        if not pool:
            unmatched.append(f"{sid} {name}")
            continue
        cents = [geom_centroid_latlng(f["geometry"]) for f in pool]
        # 複数候補が離れている場合は現座標に最も近いものを採用
        spread = max(
            math.hypot(a[0] - b[0], a[1] - b[1]) for a in cents for b in cents
        ) if len(cents) > 1 else 0.0
        if spread > 0.03 and sid in cur_coords:
            cy, cx = cur_coords[sid]
            best = min(cents, key=lambda c: math.hypot(c[0] - cy, c[1] - cx))
            new_coords[sid] = best
        else:
            lat = round(sum(c[0] for c in cents) / len(cents), 5)
            lng = round(sum(c[1] for c in cents) / len(cents), 5)
            new_coords[sid] = (lat, lng)

    print(f"[INFO] 駅照合: {len(new_coords)}/{len(station_names)} 件")
    if unmatched:
        print("[WARN] N02で見つからなかった駅:")
        for u in unmatched:
            print(f"  - {u}")

    moved = []
    for sid, (lat, lng) in new_coords.items():
        if sid in cur_coords:
            oy, ox = cur_coords[sid]
            d = math.hypot((lat - oy) * 110.57, (lng - ox) * 111.32 * math.cos(math.radians(lat)))
            if d > 0.3:
                moved.append((d, sid, station_names[sid]))
    moved.sort(reverse=True)
    print(f"\n[INFO] 0.3km以上移動する駅: {len(moved)} 件（上位20件）")
    for d, sid, name in moved[:20]:
        print(f"  {d:6.2f}km {sid} {name}")

    # ---------------- 線路沿い距離 ----------------
    # 路線ジオメトリは並行線路・ジャンクションで分断されているため、
    # セグメント端点をノードとするネットワークを路線IDごとに構築し、
    # 駅を最寄りセグメントに射影した上で Dijkstra で線路沿い最短距離を求める。
    rs_data = json.loads((data_dir / "N02-20_RailroadSection.geojson").read_text(encoding="utf-8"))
    segs_by_n02: dict[str, list[LineString]] = {}
    need_lines = {n for v in LINE_ID_TO_N02.values() for n in v}
    for f in rs_data["features"]:
        n02_line = f["properties"].get("N02_003") or ""
        if n02_line not in need_lines:
            continue
        if JRW_OPERATOR not in (f["properties"].get("N02_004") or ""):
            continue
        g = shape(f["geometry"])
        parts = list(g.geoms) if isinstance(g, MultiLineString) else [g]
        segs_by_n02.setdefault(n02_line, []).extend(to_km(p) for p in parts)
    for n02_line in sorted(need_lines - set(segs_by_n02)):
        print(f"[WARN] 線路データなし: {n02_line}")

    class RailNet:
        """線路ポリラインの頂点をノードとしたネットワーク。

        頂点を5mグリッドで統合してフィーチャ間の端点誤差を吸収し、
        線路沿い最短距離を営業キロの近似として得る。
        グリッドを粗くすると蛇行区間で誤ショートカットが生じるので注意。
        """

        CELL = 0.005  # ノード統合グリッド (km)

        def __init__(self, segs: list[LineString]):
            self.adj: dict[tuple, dict[tuple, float]] = {}
            self.vertices: list[tuple[float, float, tuple]] = []
            for seg in segs:
                prev_key = None
                prev_c = None
                for c in seg.coords:
                    key = (round(c[0] / self.CELL), round(c[1] / self.CELL))
                    self.vertices.append((c[0], c[1], key))
                    if prev_key is not None and key != prev_key:
                        w = math.hypot(c[0] - prev_c[0], c[1] - prev_c[1])
                        na = self.adj.setdefault(prev_key, {})
                        nb = self.adj.setdefault(key, {})
                        if key not in na or w < na[key]:
                            na[key] = w
                            nb[prev_key] = w
                    prev_key, prev_c = key, c

        def snap_nodes(self, pt: Point, max_km: float) -> dict[tuple, float]:
            """半径 max_km 内の頂点ノード → 駅からの直線距離(km)"""
            px, py = pt.x, pt.y
            hits: dict[tuple, float] = {}
            for x, y, key in self.vertices:
                d = math.hypot(x - px, y - py)
                if d <= max_km and (key not in hits or d < hits[key]):
                    hits[key] = d
            return hits

        def dist(self, pa: Point, pb: Point, max_snap_km: float) -> float | None:
            import heapq
            starts = self.snap_nodes(pa, max_snap_km)
            goals = self.snap_nodes(pb, max_snap_km)
            if not starts or not goals:
                return None
            best = None
            pq = [(d, n) for n, d in starts.items()]
            heapq.heapify(pq)
            dist_map: dict[tuple, float] = {}
            while pq:
                d, n = heapq.heappop(pq)
                if best is not None and d >= best:
                    break  # これ以上短くならない
                if n in dist_map:
                    continue
                dist_map[n] = d
                if n in goals:
                    total = d + goals[n]
                    if best is None or total < best:
                        best = total
                for m, w in self.adj.get(n, {}).items():
                    if m not in dist_map:
                        heapq.heappush(pq, (d + w, m))
            return best

    nets: dict[str, RailNet] = {}
    for lid, n02_names in LINE_ID_TO_N02.items():
        segs = [s for n in n02_names for s in segs_by_n02.get(n, [])]
        if segs:
            nets[lid] = RailNet(segs)

    snap_cache: dict[tuple[str, str], Point] = {}

    def station_pt(sid: str) -> Point | None:
        p = new_coords.get(sid) or cur_coords.get(sid)
        if not p:
            return None
        return Point(p[1] * 111.32 * REF_COS, p[0] * 110.57)

    def along_dist(sid_a: str, sid_b: str, lid: str) -> float | None:
        net = nets.get(lid)
        if net is None:
            return None
        pa, pb = station_pt(sid_a), station_pt(sid_b)
        if pa is None or pb is None:
            return None
        return net.dist(pa, pb, args.max_snap_km)

    dist_updates: dict[int, float] = {}   # 行index → 新distance
    dist_report = []
    dist_missing = []
    for b in blocks:
        entries = b["entries"]
        for i in range(len(entries) - 1):
            li, sid, name, old = entries[i]
            _, nsid, nname, _ = entries[i + 1]
            if sid == nsid:
                continue
            d = along_dist(sid, nsid, b["lid"])
            if d is None:
                dist_missing.append(f"{b['lid']} {name}→{nname} (旧 {old}km)")
                continue
            newd = max(0.1, round(d, 1))
            dist_updates[li] = newd
            if abs(newd - old) > 0.05:
                dist_report.append((abs(newd - old), b["lid"], name, nname, old, newd))

    print(f"\n[INFO] 距離更新対象エッジ: {len(dist_updates)} 件 / 変化あり {len(dist_report)} 件")
    if dist_missing:
        print("[WARN] 線路沿い距離を計算できなかったエッジ（現状維持）:")
        for m in dist_missing:
            print(f"  - {m}")
    dist_report.sort(reverse=True)
    print("[INFO] 距離変化の大きい順:")
    for diff, lid, name_a, name_b, old, new in dist_report:
        print(f"  {lid:3} {name_a}→{name_b}: {old}km → {new}km")

    if not args.write:
        print("\n[INFO] --write 未指定のため generate_graph.py は変更していません")
        return

    # ---------------- 書き換え ----------------
    for sid, (lat, lng) in new_coords.items():
        if sid not in coord_lines:
            continue
        li = coord_lines[sid]
        m = COORD_RE.match(lines[li])
        lines[li] = f'{m.group(1)}"{sid}": ({lat}, {lng}){m.group(5)}{m.group(6) or ""}'
    for li, newd in dist_updates.items():
        m = ENTRY_RE.match(lines[li])
        lines[li] = f"{m.group(1)}{newd}{m.group(5)}"

    GRAPH_PY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[INFO] 書き換え完了: {GRAPH_PY}")
    print("[INFO] 続けて backend/generate_graph.py を実行して graph.json を再生成してください")


if __name__ == "__main__":
    main()
