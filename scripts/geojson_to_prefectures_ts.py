#!/usr/bin/env python3
"""
kinki_prefectures.geojson（N03由来の府県ポリゴン） → frontend/src/data/prefectures.ts 生成

RouteMap.tsx が使う既存フォーマット（{name, fill, coords:[lat,lng][]}・単一リング）を
維持したまま、座標だけ N03 由来の正確な輪郭へ差し替える。各府県は最大の外周リング
（＝主島）のみを採用し、RDP で地図表示向けの点数まで簡略化する。

Usage:
  python scripts/geojson_to_prefectures_ts.py [input.geojson] [options]

Options:
  -o, --output FILE    出力 TS（デフォルト: frontend/src/data/prefectures.ts）
  --epsilon FLOAT      RDP 簡略化の閾値（度, デフォルト: 0.012 ≈ 1.2km）
"""

import argparse
import io
import json
import math
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 表示名（N03_001 から 県/府 を除去した短縮形）→ 塗り色。現行 prefectures.ts の色を踏襲。
FILL = {
    "三重":   "#6ee7b7",
    "滋賀":   "#7dd3fc",
    "京都":   "#c4b5fd",
    "大阪":   "#fca5a5",
    "兵庫":   "#818cf8",
    "奈良":   "#fde68a",
    "和歌山": "#fdba74",
    "福井":   "#f9a8d4",  # 新規追加（隣接の滋賀=空色/京都=紫と被らない桃色）
}

# 出力順（現行踏襲＋末尾に福井）
ORDER = ["三重", "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山", "福井"]


def short_name(n03_001: str) -> str:
    """都道府県名から末尾の 都/道/府/県 を除去。"""
    return n03_001[:-1] if n03_001 and n03_001[-1] in "都道府県" else n03_001


def rdp(points, epsilon):
    """Ramer-Douglas-Peucker 簡略化。"""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        dists = [math.hypot(p[0] - start[0], p[1] - start[1]) for p in points[1:-1]]
    else:
        dists = [abs(dx * (start[1] - p[1]) - (start[0] - p[0]) * dy) / length
                 for p in points[1:-1]]
    max_dist = max(dists)
    max_idx = dists.index(max_dist) + 1
    if max_dist > epsilon:
        left = rdp(points[:max_idx + 1], epsilon)
        right = rdp(points[max_idx:], epsilon)
        return left[:-1] + right
    return [start, end]


def largest_outer_ring(geometry):
    """Polygon / MultiPolygon から最大の外周リング（[lng,lat]）を取り出す。"""
    t = geometry["type"]
    if t == "Polygon":
        rings = [geometry["coordinates"][0]]
    elif t == "MultiPolygon":
        rings = [poly[0] for poly in geometry["coordinates"]]
    else:
        raise ValueError(f"Unsupported geometry: {t}")
    return max(rings, key=len)


def simplify_ring(ring_lnglat, epsilon):
    """[lng,lat] の外周 → RDP 簡略化した (lat,lng) リスト（閉じ重複なし）。"""
    pts = [(c[1], c[0]) for c in ring_lnglat]  # [lng,lat] → (lat,lng)
    simplified = rdp(pts, epsilon)
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified[:-1]  # TS 配列では閉じ重複を落とす


def generate_ts(prefs_data) -> str:
    lines = [
        "export interface PrefectureData {",
        "  name: string;",
        "  fill: string;",
        "  coords: [number, number][]; // [lat, lng]",
        "}",
        "",
        "const PREFECTURES: PrefectureData[] = [",
    ]
    for name, fill, coords in prefs_data:
        coord_strs = [f"    [{lat:.5f}, {lng:.5f}]" for lat, lng in coords]
        lines.append("  {")
        lines.append(f'    name: "{name}",')
        lines.append(f'    fill: "{fill}",')
        lines.append("    coords: [")
        lines.append(",\n".join(coord_strs))
        lines.append("    ],")
        lines.append("  },")
    lines.append("];")
    lines.append("")
    lines.append("export default PREFECTURES;")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="府県 geojson → prefectures.ts 生成")
    parser.add_argument("input", nargs="?", default="kinki_prefectures.geojson",
                        help="入力 geojson（デフォルト: kinki_prefectures.geojson）")
    parser.add_argument("-o", "--output", default="frontend/src/data/prefectures.ts",
                        help="出力 TS パス")
    parser.add_argument("--epsilon", type=float, default=0.012,
                        help="RDP 簡略化閾値（度, デフォルト 0.012）")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[ERROR] 入力が見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        gj = json.load(f)

    by_name = {}
    for feat in gj["features"]:
        name = short_name((feat.get("properties") or {}).get("N03_001", ""))
        ring = largest_outer_ring(feat["geometry"])
        simp = simplify_ring(ring, args.epsilon)
        by_name[name] = (len(ring), simp)

    prefs_data = []
    print(f"{'府県':<8}{'元点数':>8}{'簡略後':>8}")
    print("-" * 26)
    for name in ORDER:
        if name not in by_name:
            print(f"[WARN] geojson に {name} がありません（スキップ）", file=sys.stderr)
            continue
        orig, simp = by_name[name]
        fill = FILL.get(name, "#cccccc")
        prefs_data.append((name, fill, simp))
        print(f"{name:<8}{orig:>8,}{len(simp):>8,}")

    ts = generate_ts(prefs_data)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(ts)

    total = sum(len(c) for _, _, c in prefs_data)
    print("-" * 26)
    print(f"{'合計':<8}{'':>8}{total:>8,}")
    print(f"[INFO] 出力: {args.output}（{len(prefs_data)} 府県・計 {total:,} 点）")


if __name__ == "__main__":
    main()
