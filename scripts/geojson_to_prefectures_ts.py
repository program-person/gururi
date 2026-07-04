#!/usr/bin/env python3
"""
kinki_prefectures.geojson（N03由来の府県ポリゴン） → frontend/src/data/prefectures.ts 生成

入力 geojson は mapshaper のトポロジー保持 simplify 済みであることを前提とし、
このスクリプトでは追加の簡略化を一切行わない（座標をそのまま転記する）。
府県ごとに独立した簡略化（RDP など）を挟むと隣接県で残る頂点が食い違い、
県境に隙間や重なりが生じるため厳禁。点数を減らしたい場合は mapshaper 側で行う:

  npx mapshaper kinki_prefectures.geojson -simplify interval=300 keep-shapes \
      -o kinki_simplified.geojson

各府県は複数リング（本土＋島）を保持する。面積が --min-area km² 未満の
小リング（小島・埋立地など）は除外する。

Usage:
  python scripts/geojson_to_prefectures_ts.py [input.geojson] [options]

Options:
  -o, --output FILE    出力 TS（デフォルト: frontend/src/data/prefectures.ts）
  --min-area FLOAT     リング採用の最小面積 km²（デフォルト: 20.0。最大リングは常に採用）
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
    "福井":   "#f9a8d4",
}

# 出力順（現行踏襲＋末尾に福井）
ORDER = ["三重", "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山", "福井"]

KM_PER_DEG_LAT = 111.32


def short_name(n03_001: str) -> str:
    """都道府県名から末尾の 都/道/府/県 を除去。"""
    return n03_001[:-1] if n03_001 and n03_001[-1] in "都道府県" else n03_001


def ring_area_km2(ring_lnglat) -> float:
    """外周リング（[lng,lat]）の面積を km² で返す（シューレース＋緯度補正）。"""
    if len(ring_lnglat) < 4:
        return 0.0
    mean_lat = sum(c[1] for c in ring_lnglat) / len(ring_lnglat)
    kx = KM_PER_DEG_LAT * math.cos(math.radians(mean_lat))  # km / 経度1度
    ky = KM_PER_DEG_LAT                                     # km / 緯度1度
    s = 0.0
    for i in range(len(ring_lnglat) - 1):
        x1, y1 = ring_lnglat[i][0] * kx, ring_lnglat[i][1] * ky
        x2, y2 = ring_lnglat[i + 1][0] * kx, ring_lnglat[i + 1][1] * ky
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def outer_rings(geometry):
    """Polygon / MultiPolygon から外周リング（[lng,lat]）のリストを取り出す。"""
    t = geometry["type"]
    if t == "Polygon":
        return [geometry["coordinates"][0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    raise ValueError(f"Unsupported geometry: {t}")


def to_latlng(ring_lnglat):
    """[lng,lat] リング → (lat,lng) リスト（閉じ重複を落とす）。"""
    pts = [(c[1], c[0]) for c in ring_lnglat]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def generate_ts(prefs_data) -> str:
    lines = [
        "export interface PrefectureData {",
        "  name: string;",
        "  fill: string;",
        "  // [lat, lng] のリング配列。rings[0] が本土（最大リング）、以降は島。",
        "  rings: [number, number][][];",
        "}",
        "",
        "const PREFECTURES: PrefectureData[] = [",
    ]
    for name, fill, rings in prefs_data:
        lines.append("  {")
        lines.append(f'    name: "{name}",')
        lines.append(f'    fill: "{fill}",')
        lines.append("    rings: [")
        for ring in rings:
            coord_strs = [f"      [{lat:.5f}, {lng:.5f}]" for lat, lng in ring]
            lines.append("      [")
            lines.append(",\n".join(coord_strs))
            lines.append("      ],")
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
    parser.add_argument("--min-area", type=float, default=20.0,
                        help="リング採用の最小面積 km²（デフォルト 20.0）")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[ERROR] 入力が見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        gj = json.load(f)

    by_name = {}
    for feat in gj["features"]:
        name = short_name((feat.get("properties") or {}).get("N03_001", ""))
        rings = outer_rings(feat["geometry"])
        scored = sorted(((ring_area_km2(r), r) for r in rings),
                        key=lambda x: x[0], reverse=True)
        # 最大リング（本土）は常に採用、残りは面積閾値で選別
        kept = [scored[0]] + [(a, r) for a, r in scored[1:] if a >= args.min_area]
        by_name[name] = (
            sum(len(r) for r in rings),
            [(a, to_latlng(r)) for a, r in kept],
        )

    prefs_data = []
    print(f"{'府県':<8}{'元点数':>8}{'採用リング':>10}{'採用点数':>8}")
    print("-" * 36)
    for name in ORDER:
        if name not in by_name:
            print(f"[WARN] geojson に {name} がありません（スキップ）", file=sys.stderr)
            continue
        orig, kept = by_name[name]
        rings = [r for _, r in kept]
        prefs_data.append((name, FILL.get(name, "#cccccc"), rings))
        npts = sum(len(r) for r in rings)
        print(f"{name:<8}{orig:>8,}{len(rings):>10}{npts:>8,}")

    ts = generate_ts(prefs_data)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(ts)

    total = sum(len(r) for _, _, rings in prefs_data for r in rings)
    print("-" * 36)
    print(f"[INFO] 出力: {args.output}（{len(prefs_data)} 府県・計 {total:,} 点）")


if __name__ == "__main__":
    main()
