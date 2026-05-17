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
│   │   └── config.py      # pydantic-settings 設定
│   ├── data/
│   │   ├── graph.json     # 大阪近郊区間 主要路線データ（192駅・200エッジ）
│   │   └── fare_table.json # キロ程→IC/きっぷ運賃テーブル
│   ├── tests/
│   ├── generate_graph.py  # graph.json を再生成するスクリプト
│   └── requirements.txt
└── frontend/
    └── src/
        ├── app/page.tsx       # トップページ（検索UI）
        ├── components/
        │   ├── StationSearch.tsx  # 駅名オートコンプリート
        │   └── RouteCard.tsx      # ルート1件の表示カード
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
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | バックエンドAPIのURL |

## バックエンド アーキテクチャ

### 起動時の処理
`lifespan` で `graph.json` と `fare_table.json` を読み込み、`RailState`（frozen dataclass）として `app.state.rail` に保持。

### エンドポイント一覧

| エンドポイント | 説明 |
|---|---|
| `GET /stations` | 全駅リスト |
| `GET /route` | 最短経路（Dijkstra） |
| `GET /fare` | 2駅間の直線運賃 |
| `GET /omawari` | 大回りルート候補（最長ルート優先） |
| `GET /omawari/by-fare` | 運賃指定での大回りルート候補 |
| `GET /health` | ヘルスチェック |

### 大回りアルゴリズム（`omawari.py`）
- ランダム化DFS + 枝刈り（同一駅再訪禁止・時間上限・駅数上限）
- `find_omawari_routes`: 任意のエンドポイントへの最長ルートを `num_trials` 回試行
- `find_omawari_by_fare`: 出発駅から `max_km` 以内の駅に到達する全ルートをDFS中にスナップショット保存

### データモデル（`models.py`）
Pydantic モデルは JSON camelCase / Python snake_case で相互変換（`populate_by_name=True`）。

### グラフデータ（`generate_graph.py`）
路線データを Python スクリプトで管理。データを変更したい場合は `generate_graph.py` を編集して実行する（`graph.json` を手編集しない）。

## フロントエンド アーキテクチャ

- `api.ts`: fetch ラッパー。バックエンドの各エンドポイントに対応する関数を提供
- `StationSearch.tsx`: 駅名インクリメンタルサーチ（クライアントサイドフィルタリング）
- `RouteCard.tsx`: 1ルートの概要表示 + `<details>` で経路詳細を展開

## 対象路線

大阪環状線(C)・JR京都線＋琵琶湖線(A)・JR神戸線(JK)・JR宝塚線(G)・JR東西線(T)・学研都市線(H)・大和路線(Q)・おおさか東線(F)・阪和線(R)・奈良線(D)・湖西線(KS)・北陸本線(NR)・草津線(KB)・関西本線非電化(KN)・嵯峨野線(E)・桜井線(U)・和歌山線(W)・羽衣支線(HA)

## 未実装（Phase 5）

- 乗換案内（実ダイヤ・時刻表連携）— データソース未定（GTFS-JP 候補）
- ルート可視化（路線図ベースの SVG/マップ）
