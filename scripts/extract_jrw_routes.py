#!/usr/bin/env python3
"""
国土数値情報 N02 鉄道GeoJSON → JR西日本 大回り対象路線 抽出スクリプト

Usage:
  python scripts/extract_jrw_routes.py <input.geojson> [options]

Options:
  -o, --output FILE       出力ファイルパス (デフォルト: jrw_routes.geojson)
  --tolerance FLOAT       Shapely simplify トレランス (デフォルト: 0.001 ≈ 111m)
  --inspect               全運営機関・路線名を一覧表示して終了（フィルタ前確認用）
  --no-target-filter      JR西日本の全路線を出力（対象絞り込みなし）

Requirements:
  pip install shapely

N02 プロパティ仕様:
  N02_001: 種別コード (2=JR在来線)
  N02_002: 路線名
  N02_003: 運営機関
  N02_004: 路線区間
"""

import argparse
import io
import json
import sys
from collections import defaultdict

# Windows コンソールの文字化け防止
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    from shapely.geometry import shape, mapping, MultiLineString, LineString
    from shapely.ops import unary_union
except ImportError:
    print("ERROR: shapely が必要です: pip install shapely", file=sys.stderr)
    sys.exit(1)


# -----------------------------------------------------------------------
# N02-20 プロパティ実態（inspect で確認済み）
#   N02_001: 年度コード
#   N02_002: 種別コード (1=新幹線, 2=JR在来線, 3=公営, 4=民鉄, 5=三セク)
#   N02_003: 路線名
#   N02_004: 運営機関名
# -----------------------------------------------------------------------

JRW_OPERATOR = "西日本旅客鉄道"

# -----------------------------------------------------------------------
# 対象路線: N02_003（路線名）→ 愛称（アプリ内表記）
# N02-20 実データで確認した正式路線名を使用
# -----------------------------------------------------------------------
TARGET_LINE_ALIAS: dict[str, str] = {
    "大阪環状線":   "大阪環状線",
    "桜島線":       "大阪環状線",              # 大阪環状線に含まれる支線
    "東海道線":     "JR京都線/JR神戸線/JR琵琶湖線",
    "山陽線":       "JR神戸線",                # N02は「山陽本線」でなく「山陽線」
    "福知山線":     "JR宝塚線",
    "JR東西線":     "JR東西線",                # N02は「東西線」でなく「JR東西線」
    "片町線":       "学研都市線",
    "関西線":       "大和路線/関西本線(非電化)", # N02は「関西本線」でなく「関西線」
    "おおさか東線": "おおさか東線",
    "阪和線":       "阪和線",
    "関西空港線":   "関西空港線",              # 阪和線から分岐
    "奈良線":       "奈良線",
    "湖西線":       "湖西線",
    "北陸線":       "北陸本線",                # N02は「北陸本線」でなく「北陸線」
    "草津線":       "草津線",
    "山陰線":       "嵯峨野線",                # N02は「山陰本線」でなく「山陰線」
    "桜井線":       "桜井線",
    "和歌山線":     "和歌山線",
    "紀勢線":       "きのくに線",              # N02は「紀勢本線」でなく「紀勢線」
    # 羽衣支線: N02-20 に独立エントリなし（阪和線に含まれる）
}

TARGET_LINES = set(TARGET_LINE_ALIAS.keys())


def is_jrw_operator(operator: str) -> bool:
    return JRW_OPERATOR in operator


def get_props(props: dict) -> tuple[str, str, str]:
    """(路線名, 運営機関, 種別コード) を返す"""
    return (
        props.get("N02_003") or "",   # 路線名
        props.get("N02_004") or "",   # 運営機関
        props.get("N02_002") or "",   # 種別コード
    )


def count_coords(geom_dict: dict) -> int:
    """GeoJSON geometry dict の座標点数を数える"""
    t = geom_dict.get("type", "")
    coords = geom_dict.get("coordinates", [])
    if t == "LineString":
        return len(coords)
    if t == "MultiLineString":
        return sum(len(ring) for ring in coords)
    return 0


def simplify_geometry(geom_dict: dict, tolerance: float) -> dict:
    """shapely で simplify して GeoJSON dict に戻す。3D座標は2Dに落とす。"""
    # 3D座標 [lon, lat, elev] を [lon, lat] に正規化
    geom_dict = drop_z(geom_dict)
    geom = shape(geom_dict)
    simplified = geom.simplify(tolerance, preserve_topology=True)
    return mapping(simplified)


def drop_z(geom_dict: dict) -> dict:
    """座標から Z 値を除去して 2D GeoJSON に変換"""
    t = geom_dict.get("type", "")
    coords = geom_dict.get("coordinates", [])
    if t == "LineString":
        return {"type": t, "coordinates": [[c[0], c[1]] for c in coords]}
    if t == "MultiLineString":
        return {"type": t, "coordinates": [[[c[0], c[1]] for c in ring] for ring in coords]}
    return geom_dict


def main():
    parser = argparse.ArgumentParser(description="N02 GeoJSON から JR西日本路線を抽出")
    parser.add_argument(
        "input",
        nargs="?",
        default=r"C:\Users\hirom\Desktop\N02-20_GML\N02-20_RailroadSection.geojson",
        help="入力 GeoJSON ファイルパス",
    )
    parser.add_argument("-o", "--output", default="jrw_routes.geojson", help="出力ファイルパス")
    parser.add_argument("--tolerance", type=float, default=0.001, help="simplify トレランス (度)")
    parser.add_argument("--inspect", action="store_true", help="路線名・運営機関を一覧表示して終了")
    parser.add_argument("--no-target-filter", action="store_true", help="JR西日本全路線を出力")
    args = parser.parse_args()

    print(f"[INFO] 読み込み中: {args.input}")
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    print(f"[INFO] 総フィーチャ数: {len(features):,}")

    # --inspect: 運営機関・路線名の一覧だけ出力
    if args.inspect:
        operators: dict[str, set] = defaultdict(set)
        for feat in features:
            props = feat.get("properties") or {}
            line, op, kind = get_props(props)
            operators[op].add(line)
        print("\n=== 運営機関 × 路線名 一覧 ===")
        for op in sorted(operators):
            marker = "← JR西" if is_jrw_operator(op) else ""
            print(f"\n[{op}] {marker}")
            for line in sorted(operators[op]):
                hit = "  ✓" if line in TARGET_LINES else ""
                print(f"  {line}{hit}")
        return

    # JR西日本フィルタ
    jrw_features = [
        f for f in features
        if is_jrw_operator((f.get("properties") or {}).get("N02_004") or "")
    ]
    print(f"[INFO] JR西日本フィーチャ数: {len(jrw_features):,}")

    # 対象路線フィルタ
    if args.no_target_filter:
        target_features = jrw_features
    else:
        target_features = [
            f for f in jrw_features
            if ((f.get("properties") or {}).get("N02_003") or "") in TARGET_LINES
        ]
        print(f"[INFO] 対象路線フィルタ後: {len(target_features):,} フィーチャ")

    if not target_features:
        print("[WARN] フィーチャが 0 件です。--inspect で路線名を確認してください。", file=sys.stderr)
        sys.exit(1)

    # ジオメトリを simplify しながら出力フィーチャを構築
    out_features = []
    stats_by_line: dict[str, dict] = defaultdict(lambda: {"features": 0, "pts_before": 0, "pts_after": 0})

    for feat in target_features:
        props = feat.get("properties") or {}
        line, op, kind = get_props(props)
        section = props.get("N02_001") or ""
        geom_orig = feat.get("geometry")
        if not geom_orig:
            continue

        pts_before = count_coords(geom_orig)
        geom_simplified = simplify_geometry(geom_orig, args.tolerance)
        pts_after = count_coords(geom_simplified)

        alias = TARGET_LINE_ALIAS.get(line, line)

        out_features.append({
            "type": "Feature",
            "properties": {
                "route":    line,
                "alias":    alias,
                "operator": op,
                "section":  section,
            },
            "geometry": geom_simplified,
        })

        s = stats_by_line[line]
        s["features"] += 1
        s["pts_before"] += pts_before
        s["pts_after"] += pts_after

    # 出力
    out_geojson = {
        "type": "FeatureCollection",
        "features": out_features,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out_geojson, f, ensure_ascii=False, separators=(",", ":"))

    # ログ
    print(f"\n=== 変換結果サマリ (tolerance={args.tolerance}) ===")
    print(f"{'路線名':<16} {'愛称':<24} {'feat':>5} {'pts_before':>10} {'pts_after':>9} {'削減率':>7}")
    print("-" * 78)
    total_before = total_after = 0
    for line in sorted(stats_by_line):
        s = stats_by_line[line]
        alias = TARGET_LINE_ALIAS.get(line, line)
        before = s["pts_before"]
        after = s["pts_after"]
        ratio = (1 - after / before) * 100 if before else 0
        total_before += before
        total_after += after
        print(f"{line:<16} {alias:<24} {s['features']:>5} {before:>10,} {after:>9,} {ratio:>6.1f}%")
    print("-" * 78)
    total_ratio = (1 - total_after / total_before) * 100 if total_before else 0
    print(f"{'合計':<42} {total_before:>10,} {total_after:>9,} {total_ratio:>6.1f}%")
    print(f"\n[INFO] 路線数: {len(stats_by_line)} / 対象 {len(TARGET_LINES)}")

    missing = TARGET_LINES - set(stats_by_line.keys())
    if missing:
        print(f"[WARN] 以下の路線が出力に含まれていません（データ欠損または路線名不一致）:")
        for m in sorted(missing):
            print(f"  - {m}")

    print(f"[INFO] 出力完了: {args.output} ({len(out_features)} フィーチャ)")
    print(f"\n→ geojson.io で確認: https://geojson.io/")
    print(f"  出力ファイルをブラウザにドラッグ＆ドロップしてください")


if __name__ == "__main__":
    main()
