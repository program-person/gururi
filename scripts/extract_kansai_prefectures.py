#!/usr/bin/env python3
"""
国土数値情報 N03 行政区域GeoJSON → 関西圏 都道府県ポリゴン抽出スクリプト
（mapshaper CLI ラッパー）

処理パイプライン（mapshaper CLI に委譲）:
  1. 都道府県名(N03_001)で dissolve  … 市区町村ポリゴンを都道府県単位に統合
  2. simplify（トポロジー保持・保持率は引数指定）… 隣接境界を共有したまま間引き
  3. 対象府県のみ filter             … 関西2府4県 + 三重 + 福井 を抽出

  ※ mapshaper の -simplify は既定でトポロジー保持（共有境界を一貫して簡略化）。
  ※ 1→2 を全国に対して行ってから 3 で抽出するため、抽出領域の外周（除外県との
    境界）も隣接形状を考慮して簡略化され、ギザつきが出にくい。

対象府県（8）:
  関西2府4県 = 大阪府・京都府(2府) ＋ 兵庫県・奈良県・和歌山県・滋賀県(4県)
  追加       = 三重県・福井県

Usage:
  python scripts/extract_kansai_prefectures.py <input_N03.geojson> [options]

Options:
  -o, --output FILE     出力 GeoJSON（デフォルト: kansai_prefectures.geojson）
  -r, --retention PCT   simplify 保持率 %（デフォルト: 10。"10" でも "10%" でも可）
  --pref-field NAME     都道府県名フィールド（デフォルト: N03_001）
  --no-keep-shapes      小ポリゴン（離島など）の消失を許可（既定は keep-shapes 有効）
  --filter-first        dissolve 前に対象府県へ絞り込む（全国 N03 が巨大な場合の高速化用。
                        ※ 簡略化トポロジーが対象府県内のみで構築される点が既定と異なる）
  --mapshaper-js PATH   mapshaper 本体(JS)のパスを明示指定
  --dry-run             実行せず、組み立てた mapshaper コマンドを表示するだけ

Requirements:
  Node.js ＋ mapshaper（`npx mapshaper` が動けば OK。グローバル/ローカル/npx
  キャッシュのいずれかにあれば自動検出する）

N03 プロパティ仕様（行政区域データ）:
  N03_001: 都道府県名   N03_002: 支庁・振興局名
  N03_003: 郡・政令市名 N03_004: 市区町村名   N03_007: 行政区域コード
"""

import argparse
import glob
import io
import json
import os
import subprocess
import sys

# Windows コンソールの文字化け防止
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# -----------------------------------------------------------------------
# 対象府県（N03_001 の値と完全一致させる）
# -----------------------------------------------------------------------
TARGET_PREFS = [
    "大阪府", "京都府",                    # 関西2府
    "兵庫県", "奈良県", "和歌山県", "滋賀県",  # 関西4県
    "三重県", "福井県",                    # 追加
]


def _run_text(cmd: str) -> str:
    """ASCII のみのメタデータ取得用。shell=True で気軽に叩く（メタ文字なし）。"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def resolve_mapshaper_js(explicit: str | None) -> str | None:
    """mapshaper 本体(JS)を探す。node から直接起動するため .cmd シムは使わない。"""
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    env = os.environ.get("MAPSHAPER_JS")
    if env and os.path.isfile(env):
        return env

    candidates = [os.path.join("node_modules", "mapshaper", "bin", "mapshaper")]
    groot = _run_text("npm root -g")
    if groot:
        candidates.append(os.path.join(groot, "mapshaper", "bin", "mapshaper"))
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    # npx キャッシュ（npx mapshaper を一度でも実行していればここに入る）
    cache = _run_text("npm config get cache")

    def _glob_cache() -> str | None:
        if not cache:
            return None
        hits = glob.glob(os.path.join(
            cache, "_npx", "*", "node_modules", "mapshaper", "bin", "mapshaper"))
        return hits[0] if hits else None

    found = _glob_cache()
    if found:
        return found

    # 未キャッシュなら npx で取得させてから再探索
    print("[INFO] mapshaper が見つからないため npx で取得を試みます ...")
    subprocess.run("npx --yes mapshaper --version", shell=True, capture_output=True)
    return _glob_cache()


def build_mapshaper_args(input_path: str, output_path: str, retention: float,
                         pref_field: str, keep_shapes: bool,
                         filter_first: bool) -> list[str]:
    """mapshaper に渡す引数列を組み立てる（node 経由・shell=False 前提）。"""
    # 日本語値は \uXXXX へエスケープしてコマンド全体を ASCII 化（取りこぼし防止）
    names_js = json.dumps(TARGET_PREFS, ensure_ascii=True)
    # ">" を避けて includes() を使用（将来 shell 経由でも壊れにくい）
    filter_expr = f"{names_js}.includes({pref_field})"

    dissolve = ["-dissolve", pref_field]
    simplify = ["-simplify", f"{retention}%"] + (["keep-shapes"] if keep_shapes else [])
    flt = ["-filter", filter_expr]

    if filter_first:
        pipeline = flt + dissolve + simplify
    else:
        pipeline = dissolve + simplify + flt

    return [input_path, *pipeline, "-o", output_path, "format=geojson"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="N03 行政区域 GeoJSON から関西圏の都道府県ポリゴンを抽出（mapshaper CLI）")
    parser.add_argument("input", help="入力 N03 GeoJSON ファイルパス")
    parser.add_argument("-o", "--output", default="kansai_prefectures.geojson",
                        help="出力ファイルパス")
    parser.add_argument("-r", "--retention", default="10",
                        help="simplify 保持率 %%（例: 10 / 10%%）")
    parser.add_argument("--pref-field", default="N03_001",
                        help="都道府県名フィールド（デフォルト: N03_001）")
    parser.add_argument("--no-keep-shapes", action="store_true",
                        help="小ポリゴンの消失を許可（既定は keep-shapes 有効）")
    parser.add_argument("--filter-first", action="store_true",
                        help="dissolve 前に対象府県へ絞り込む（巨大入力の高速化用）")
    parser.add_argument("--mapshaper-js", default=None,
                        help="mapshaper 本体(JS)のパスを明示指定")
    parser.add_argument("--dry-run", action="store_true",
                        help="実行せずコマンドを表示するだけ")
    args = parser.parse_args()

    # 保持率の正規化（"10%" → 10.0）
    try:
        retention = float(str(args.retention).strip().rstrip("%"))
    except ValueError:
        print(f"[ERROR] 保持率が数値ではありません: {args.retention!r}", file=sys.stderr)
        sys.exit(1)
    if not (0 < retention <= 100):
        print(f"[ERROR] 保持率は 0〜100 の範囲で指定してください: {retention}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.input) and not args.dry_run:
        print(f"[ERROR] 入力ファイルが見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)

    ms_args = build_mapshaper_args(
        input_path=args.input,
        output_path=args.output,
        retention=retention,
        pref_field=args.pref_field,
        keep_shapes=not args.no_keep_shapes,
        filter_first=args.filter_first,
    )

    order = ("filter → dissolve → simplify" if args.filter_first
             else "dissolve → simplify → filter")
    print(f"[INFO] 対象府県: {' / '.join(TARGET_PREFS)}")
    print(f"[INFO] 処理順:   {order}")
    print(f"[INFO] 保持率:   {retention}%（{'keep-shapes 有効' if not args.no_keep_shapes else 'keep-shapes なし'}）")

    # 参考用に等価な npx コマンドを表示（手動実行・確認用）
    npx_equiv = "npx mapshaper " + subprocess.list2cmdline(ms_args)
    print(f"[INFO] 等価コマンド:\n  {npx_equiv}\n")

    if args.dry_run:
        print("[INFO] --dry-run のため実行しません。")
        return

    mapshaper_js = resolve_mapshaper_js(args.mapshaper_js)
    if not mapshaper_js:
        print("[ERROR] mapshaper 本体が見つかりませんでした。\n"
              "  次のいずれかで解決してください:\n"
              "    - npm i -g mapshaper\n"
              "    - 一度 `npx mapshaper --version` を実行してキャッシュさせる\n"
              "    - --mapshaper-js <path> または環境変数 MAPSHAPER_JS で明示指定",
              file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] mapshaper: {mapshaper_js}")

    # node から直接起動（shell=False）。これでシェルのメタ文字解釈を完全に回避。
    cmd = [os.environ.get("NODE", "node"), mapshaper_js, *ms_args]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("[ERROR] node が見つかりません。Node.js を PATH に通してください。", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] mapshaper が異常終了しました (exit {e.returncode})。", file=sys.stderr)
        sys.exit(e.returncode)

    print(f"\n[INFO] 出力完了: {args.output}")
    print("→ geojson.io にドラッグ＆ドロップで確認できます: https://geojson.io/")


if __name__ == "__main__":
    main()
