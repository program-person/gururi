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
│   │   ├── omawari.py     # 大回りルート探索（ランダム化DFS）
│   │   ├── fare.py        # 運賃計算
│   │   ├── timetable.py   # 乗換案内: レッグ分割・実ダイヤ組み立て・推定フォールバック
│   │   ├── transit.py     # transit.ls8h.com API クライアント（キャッシュつき）
│   │   └── config.py      # pydantic-settings 設定
│   ├── data/
│   │   ├── graph.json     # 大阪近郊区間 主要路線データ（353駅・366エッジ・18路線ID）
│   │   ├── fare_table.json # キロ程→IC/きっぷ運賃テーブル
│   │   └── transit_station_map.json # 路線ID×駅ID → transit API 駅ID の対応表（生成物）
│   ├── tests/
│   ├── generate_graph.py  # graph.json を再生成するスクリプト
│   └── requirements.txt
├── scripts/
│   ├── extract_jrw_routes.py   # 国土数値情報N02 → 路線GeoJSON抽出
│   ├── sync_geo_from_n02.py    # N02から駅座標・駅間キロを generate_graph.py に同期
│   └── build_transit_station_map.py # transit API 駅IDマッピングを再生成（手編集しない）
└── frontend/
    └── src/
        ├── app/page.tsx       # トップページ（検索UI）
        ├── components/
        │   ├── StationSearch.tsx  # 駅名オートコンプリート
        │   ├── RouteCard.tsx      # ルート1件の表示カード
        │   └── RouteMap.tsx       # ルートの地図描画（SVG・ズーム/パン・ラベル衝突回避・路線色/凡例つき）
        └── lib/api.ts             # バックエンドAPIクライアント
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
| `GET /route` | 最短経路（Dijkstra） |
| `GET /fare` | 2駅間の直線運賃 |
| `GET /omawari` | 大回りルート候補（最長ルート優先） |
| `GET /omawari/by-fare` | 運賃指定での大回りルート候補 |
| `POST /timetable` | ルートの区間別発着時刻（実ダイヤ＋推定） |
| `GET /health` | ヘルスチェック |

### 大回りアルゴリズム（`omawari.py`）
- ランダム化DFS + 枝刈り（同一駅再訪禁止・時間上限・駅数上限）
- `find_omawari_routes`: 任意のエンドポイントへの最長ルートを `num_trials` 回試行
- `find_omawari_by_fare`: 出発駅から `max_km` 以内の駅に到達する全ルートをDFS中にスナップショット保存

### データモデル（`models.py`）
Pydantic モデルは JSON camelCase / Python snake_case で相互変換（`populate_by_name=True`）。

### グラフデータ（`generate_graph.py`）
路線データを Python スクリプトで管理。データを変更したい場合は `generate_graph.py` を編集して実行する（`graph.json` を手編集しない）。

### 乗換案内（`timetable.py` / `transit.py`）
- ルートの path を同一路線の連続区間（レッグ）に分割し、レッグごとに transit.ls8h.com API（非公式・無償・認証不要）で実ダイヤを照会。乗換0の旅程のみ採用
- 駅IDの対応表は `transit_station_map.json`（`scripts/build_transit_station_map.py --write` で再生成）
- **未収録**: 奈良線(D)・関西空港線(S)・JR東西線区間（尼崎〜京橋の東西線経由駅）。ここと API 障害時は `HEADWAY_MIN`（路線別日中運転間隔）による推定（待ち=間隔/2＋乗換歩行3分）にフォールバックし、レスポンスの `source: "estimate"` で区別
- transit API は個人運営のため、依存は `transit.py` に閉じ込めてある（差し替え・撤去はこの1ファイル＋マッピング生成のみ）

## フロントエンド アーキテクチャ

- `api.ts`: fetch ラッパー。バックエンドの各エンドポイントに対応する関数を提供
- `StationSearch.tsx`: 駅名インクリメンタルサーチ（クライアントサイドフィルタリング）
- `RouteCard.tsx`: 1ルートの概要表示 + 駅一覧・ルート図・乗換案内（出発時刻入力→区間別発着時刻表示、推定区間は「目安」バッジ）の展開
- `RouteMap.tsx`: 自前SVGの路線図。viewBox ベースのズーム・パン（ホイール/ドラッグ/ピンチ/ダブルクリック/ボタン/スライダー、最大8倍）。線幅・文字・ドットはズームしても画面上のサイズ一定で、2.2倍以上で画面内の中間駅にもラベルを表示。駅・県名・湖名ラベルは候補位置のスコアリングで衝突回避配置（表示領域基準で毎レンダー再計算）
- レイアウト: `page.tsx` の `main` は `max-w-5xl`。検索フォームは `max-w-2xl` 中央寄せ、結果カード（地図）は全幅

## 対象路線

路線IDはJR西日本公式の路線記号に準拠。A・Hは複数の愛称路線が同一IDを共有する（`/lines` はIDごとに1エントリ）。

大阪環状線(O)・JR京都線＋琵琶湖線(A)・JR神戸線(A)・北陸本線(A)・JR宝塚線(G)・JR東西線(H)・学研都市線(H)・大和路線(Q)・おおさか東線(F)・阪和線(R)・奈良線(D)・湖西線(B)・草津線(C)・関西本線非電化(V)・嵯峨野線(E)・万葉まほろば線(U)・和歌山線(T)・関西空港線(S)・羽衣支線(HA)・加古川線(I)・JRゆめ咲線(P)

駅座標・駅間キロは国土数値情報N02由来（`scripts/sync_geo_from_n02.py` で同期）。フロントの路線色（`RouteMap.tsx` の `LINE_COLORS`）と路線名フォールバック（`page.tsx` の `LINE_MAP_FALLBACK`）もこの路線IDをキーにしているため、路線IDを変更する際は両方更新すること。

## 実装済みフェーズ

- Phase 1〜4: 探索・運賃・可視化（地図）
- Phase 5: 乗換案内（transit.ls8h.com の実ダイヤ + 未収録路線は推定フォールバック）
