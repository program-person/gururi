# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JR西日本 大阪近郊区間向けの**大回り乗車**支援 Web アプリ。

- バックエンド: Python / FastAPI（`backend/`）
- フロントエンド: Next.js 15 / React（`frontend/`）

大回り乗車とは、大都市近郊区間内で同一駅を通らない限り最短区間の運賃で任意の経路を乗れる JR のルール。

## ディレクトリ構成

```
train/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI エントリポイント・全エンドポイント
│   │   ├── models.py      # Pydantic モデル
│   │   ├── graph.py       # グラフ読み込み・隣接リスト構築
│   │   ├── routing.py     # Dijkstra 最短経路
│   │   ├── omawari.py     # 大回りルート探索（3レイヤー: ウェイポイント / ゴールデンループ / FSAランダムウォーク）
│   │   ├── fare.py        # 運賃計算
│   │   ├── timetable.py   # 乗換案内: レッグ分割・実ダイヤ組み立て・推定フォールバック
│   │   ├── transit.py     # transit.ls8h.com API クライアント（キャッシュつき）
│   │   ├── ratelimit.py   # 自作スライディングウィンドウ・レート制限（IP単位）
│   │   └── config.py      # pydantic-settings 設定
│   ├── data/
│   │   ├── graph.json     # 大阪近郊区間 主要路線データ（374駅・387エッジ・20路線ID）
│   │   ├── fare_table.json # キロ程→IC/きっぷ運賃テーブル
│   │   └── transit_station_map.json # 路線ID×駅ID → transit API 駅ID の対応表（生成物）
│   ├── tests/
│   ├── generate_graph.py  # graph.json を再生成するスクリプト
│   └── requirements.txt
├── scripts/
│   ├── extract_jrw_routes.py   # 国土数値情報N02 → 路線GeoJSON抽出
│   ├── sync_geo_from_n02.py    # N02から駅座標・駅間キロを generate_graph.py に同期
│   └── build_transit_station_map.py # transit API 駅IDマッピングを再生成（手編集しない）
├── docs/
│   └── fare_calculation.md    # 運賃計算の設計判断・出典・検証記録
├── README.md                  # 全体仕様（ロジック・運賃・時刻の詳細解説）
└── frontend/
    └── src/
        ├── app/
        │   ├── layout.tsx         # 共通レイアウト・データ出典フッター
        │   ├── page.tsx           # トップページ（検索UI・結果一覧）
        │   └── timetable/page.tsx # 乗換案内（URLクエリから復元する独立ページ）
        ├── components/
        │   ├── StationSearch.tsx  # 駅名オートコンプリート
        │   ├── RouteCard.tsx      # ルート1件の表示カード
        │   └── RouteMap.tsx       # ルートの地図描画（SVG・ズーム/パン・ラベル衝突回避・路線色/凡例つき）
        └── lib/
            ├── api.ts             # バックエンドAPIクライアント
            ├── searchQuery.ts     # 検索条件 ⇄ URLクエリ変換・シード生成・遷移リンク組み立て
            └── useRailData.ts     # 駅・路線データ取得フック（LINE_MAP_FALLBACK の所在）
```

## コマンド

すべてのコマンドはプロジェクトルート（この CLAUDE.md があるディレクトリ）または各サブディレクトリから実行する。

### バックエンド（venv を有効化した状態で）

```powershell
# venv 有効化（backend/ ディレクトリから）
cd backend
.\venv\Scripts\Activate.ps1

# 依存関係インストール（初回のみ）
pip install -r requirements.txt

# 開発サーバー起動（chcp 65001 で文字化け防止）
chcp 65001
uvicorn app.main:app --reload

# テスト実行
pytest tests -v

# 単一テスト実行
pytest tests/test_route.py::test_dijkstra_by_distance -v

# グラフデータ再生成
python generate_graph.py
```

### フロントエンド

```bash
cd frontend && npm run dev     # 開発サーバー（http://localhost:3000）
cd frontend && npm run build   # プロダクションビルド
cd frontend && npx tsc --noEmit  # 型チェック
```

### 設定

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `JR_ROUTE_DATA_PATH` | `data/graph.json` | グラフデータファイルパス |
| `JR_ROUTE_ALLOW_ALL_ORIGINS` | `false` | CORS 全開放。本番はフロントの `/api` プロキシ経由（サーバー間）のため通常不要 |
| `JR_ROUTE_ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS 許可オリジン（JSON配列） |
| `JR_ROUTE_RATE_LIMIT_ENABLED` | `true` | `/omawari`・`/omawari/by-fare`・`/timetable` の IP 単位レート制限 |
| `JR_ROUTE_RATE_LIMIT_MAX_REQUESTS` | `30` | ウィンドウあたりの許可リクエスト数 |
| `JR_ROUTE_RATE_LIMIT_WINDOW_SECS` | `60.0` | レート制限ウィンドウ秒数 |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | バックエンドAPIのURL（SSR時） |
| `API_PROXY_TARGET` | 本番RailwayのURL | フロント `/api` リライトの向き先。ローカル開発では `frontend/.env.local` に `http://localhost:8000` を設定 |

## バックエンド アーキテクチャ

### 起動時の処理
`lifespan` で `graph.json` と `fare_table.json` を読み込み、`RailState`（frozen dataclass）として `app.state.rail` に保持。`transit_station_map.json` は `app.state.transit_map` に保持（無ければ空 dict = 全区間推定）。

### エンドポイント一覧

| エンドポイント | 説明 |
|---|---|
| `GET /stations` | 全駅リスト |
| `GET /lines` | 全路線リスト（路線IDごとに1エントリ） |
| `GET /route` | 最短経路（Dijkstra） |
| `GET /fare` | 2駅間の直線運賃 |
| `GET /omawari` | 大回りルート候補（最長ルート優先） |
| `GET /omawari/by-fare` | 運賃指定での大回りルート候補 |
| `POST /timetable` | ルートの区間別発着時刻（実ダイヤ＋推定） |
| `GET /health` | ヘルスチェック |

- `/omawari`・`/omawari/by-fare` は `seed`（0〜2^31-1）で乱数を固定できる。フロントはこれを URL に載せて結果を再現する
- `/timetable` は `_validate_timetable_path` でパスを検証する（駅の実在・**連続駅が指定路線の実エッジで結ばれていること**・`MAX_TIMETABLE_PATH_SEGMENTS`=400・`MAX_TIMETABLE_LEGS`=40）。外部APIへの踏み台化を防ぐため

### 大回りアルゴリズム（`omawari.py`）
- 3レイヤー: ウェイポイント（決定論）/ ゴールデンループ（定型大ループ）/ FSAランダムウォーク（DEPART・EXPLORE・RETURN の3状態）
- スコア: 路線数×10 + 距離×0.5 + 駅数×2（**路線多様性が主軸**。距離を最優先にすると同じエリアの往復が上位に来るため）
- `_merge_result_layers` でゴールデンループ枠を `GOLDEN_RESULT_RATIO`(1/3) に制限し、残りは探索由来で埋める。駅ID列で重複排除
- `find_omawari_routes`: 終着駅指定なら3レイヤー合成、指定なしは「出発駅に戻るループ」として探索し末尾1駅をトリム
- `find_omawari_by_fare`: `_random_walk_legacy` + eligible_ends（運賃から逆算した到達圏）通過時のスナップショット収集
- 詳細な重み式・アトラクター生成は README.md「ロジック: 大回りルート探索」を参照

### 運賃計算（`fare.py` / `data/fare_table.json`）
`compute_fare` の判定は**上から順に最初に当たったもの**を採用する。

1. **特定運賃**（`specificFares`・341ペア）— 発着駅ペアで決まり表引きより優先（常に表引きより安い）
2. **電車特定区間**（`denshakuStationIds`・212駅）— 全駅が区間内なら `denshaku` 表
3. 地方交通線を含まない → `trunk`（幹線）表
4. 全区間が地方交通線 → `local`（B表）
5. 混在 → 合計10km以下は `local` 表、10km超は運賃計算キロ（幹線営業キロ + 地交線×1.1）で `trunk` 表

- `localLineIds` = 加古川線(I)・播但線(J)。**地方交通線を追加したらここに登録しないと運賃がずれる**（播但線で実際に起きた）
- キロ程は1km未満切り上げ。`math.ceil(round(km, 6) - 1e-9)` の `-1e-9` は浮動小数点誤差で1帯ずれるのを防ぐため
- 関空の加算運賃は経路のO-D（区間の両端）で1回だけ適用。経由駅ごとに合算しない
- IC運賃ときっぷ運賃は常に同額（JR西は1円単位運賃未導入）
- 設計判断・出典・検証記録は `docs/fare_calculation.md` に集約

### データモデル（`models.py`）
Pydantic モデルは JSON camelCase / Python snake_case で相互変換（`populate_by_name=True`）。

### グラフデータ（`generate_graph.py`）
路線データを Python スクリプトで管理。データを変更したい場合は `generate_graph.py` を編集して実行する（`graph.json` を手編集しない）。

### 乗換案内（`timetable.py` / `transit.py`）
- ルートの path を同一路線の連続区間（レッグ）に分割し、レッグごとに transit.ls8h.com API（非公式・無償・認証不要）で実ダイヤを照会。乗換0の旅程のみ採用
- 駅IDの対応表は `transit_station_map.json`（`scripts/build_transit_station_map.py --write` で再生成）
- **未収録**: 奈良線(D)・関西空港線(S)・JR東西線区間（尼崎〜京橋の東西線経由駅）・赤穂線区間（西相生〜播州赤穂）。紀勢本線 和歌山〜和歌山市(W)は駅マッピング済みだが API が徒歩経路しか返さないため実質推定。ここと API 障害時は `HEADWAY_MIN`（路線別日中運転間隔）による推定（待ち=間隔/2＋乗換歩行3分）にフォールバックし、レスポンスの `source: "estimate"` で区別
- transit API は個人運営のため、依存は `transit.py` に閉じ込めてある（差し替え・撤去はこの1ファイル＋マッピング生成のみ）

## フロントエンド アーキテクチャ

- `api.ts`: fetch ラッパー。バックエンドの各エンドポイントに対応する関数を提供
- `searchQuery.ts`: 検索条件（`SearchQuery`）と URLクエリの相互変換。`makeSeed()` でシード生成、`timetableHref()` / `searchHref()` でページ間リンクを組み立てる。**検索状態はすべて URL に載る**ので、共有URLから同じ結果を復元できる
- `useRailData.ts`: 駅・路線データ取得フック。API 失敗時のフォールバックとして `LINE_MAP_FALLBACK`（路線ID→路線名）を持つ
- `StationSearch.tsx`: 駅名インクリメンタルサーチ（クライアントサイドフィルタリング）
- `RouteCard.tsx`: 1ルートの概要表示 + 駅一覧・ルート図の展開。乗換案内は**カード内で展開せず** `timetableHref()` のリンクで `/timetable` へ遷移する
- `app/timetable/page.tsx`: 乗換案内の独立ページ。URLクエリから検索条件を復元して `runSearch()` を再実行し、`i`番目のルートに対して `POST /timetable` を呼ぶ。推定区間は「目安」バッジ
- `app/layout.tsx`: 全ページ共通のレイアウトとデータ出典フッター。時刻表データの attribution は静的に埋め込む（transit API の `/feeds` は全国1,145件・746KB を返すが、本アプリの使用20フィードは attribution が全件同一のため動的取得しない）
- `RouteMap.tsx`: 自前SVGの路線図。viewBox ベースのズーム・パン（ホイール/ドラッグ/ピンチ/ダブルクリック/ボタン/スライダー、最大8倍）。線幅・文字・ドットはズームしても画面上のサイズ一定で、2.2倍以上で画面内の中間駅にもラベルを表示。駅・県名・湖名ラベルは候補位置のスコアリングで衝突回避配置（表示領域基準で毎レンダー再計算）
- レイアウト: `page.tsx` の `main` は `max-w-5xl`。検索フォームは `max-w-2xl` 中央寄せ、結果カード（地図）は全幅

## 対象路線

路線IDはJR西日本公式の路線記号に準拠。A・Hは複数の愛称路線が同一IDを共有する（`/lines` はIDごとに1エントリ）。

大阪環状線(O)・JR京都線＋琵琶湖線(A)・JR神戸線(A)・北陸本線(A)・JR宝塚線(G)・JR東西線(H)・学研都市線(H)・大和路線(Q)・おおさか東線(F)・阪和線(R)・奈良線(D)・湖西線(B)・草津線(C)・関西本線非電化(V)・嵯峨野線(E)・万葉まほろば線(U)・和歌山線(T)・関西空港線(S)・羽衣支線(HA)・加古川線(I)・JRゆめ咲線(P)・山陽本線 姫路〜相生(A)・赤穂線 相生〜播州赤穂(A)・播但線 姫路〜寺前(J)・紀勢本線 和歌山〜和歌山市(W)

駅座標・駅間キロは国土数値情報N02由来（`scripts/sync_geo_from_n02.py` で同期）。フロントの路線色（`RouteMap.tsx` の `LINE_COLORS`）と路線名フォールバック（`lib/useRailData.ts` の `LINE_MAP_FALLBACK`）、バックエンドの運転間隔（`timetable.py` の `HEADWAY_MIN`）もこの路線IDをキーにしているため、路線IDを変更・追加する際は全部更新すること。

## 実装済みフェーズ

- Phase 1〜4: 探索・運賃・可視化（地図）
- Phase 5: 乗換案内（transit.ls8h.com の実ダイヤ + 未収録路線は推定フォールバック）
- セキュリティ監査対応（`6544c80`）: `/timetable` パス検証・IP単位レート制限・CORSデフォルト閉鎖・transitキャッシュ上限
- 特定運賃の完全収録（`9d9e29d`）: 2025-04改定プレス別紙4から341ペアを機械転記
- 未収録路線の追加（`91e7abb`〜`0aef32c`）: ゆめ咲線(P)・山陽本線 姫路〜相生・赤穂線・播但線(J)・紀勢支線(W)。現在 374駅・387エッジ・20路線ID
- 地方交通線B表対応（`13bbc3f`）: 播但線が `localLineIds` 未登録で運賃がずれていた件を修正
- マルチプラットフォーム対応＋UI刷新（`593e70c`, `379438e`, `acd1c25`）: スマホでの横スクロール解消、鉄道サイン風デザイン
- 乗換案内の独立ページ化（`2516316`）: URLクエリで検索条件とシードを持ち回り、共有URLから同一ルートを復元
- データ出典フッター（`d0305c5`）: GTFSフィードのクレジット表示義務に対応
