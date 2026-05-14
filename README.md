# JR West Loop Route Planner (Phase 1)

FastAPI で駅・路線データから最短経路を返す API です。

## 前提

- Python 3.10 以上（3.12 以上を推奨）
- 作業ディレクトリは**常にプロジェクトのルート**（この `README.md` がある階層）
- コマンドは **venv を有効化した状態**で実行する

## 仮想環境の作成と有効化

プロジェクトルートで次を実行します。

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

コマンドプロンプトの場合:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

有効化できていると、プロンプトに `(.venv)` が付きます。

## 依存関係のインストール

```bash
pip install -r requirements.txt
```

（`fastapi`、`uvicorn`、`pydantic-settings` でアプリが起動します。`pytest` と `httpx` はテスト実行用です。）

## アプリの起動

```bash
uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000/docs` を開くと OpenAPI (Swagger) UI から `GET /route` を試せます。

## 設定（任意）

グラフ JSON のパスを変える場合、環境変数 `JR_ROUTE_DATA_PATH` にファイルの絶対パスまたはプロジェクトルートからの相対パスを指定します。未指定時は `data/graph.json` が使われます。

## テスト（任意）

venv を有効化したまま:

```bash
pytest tests -v
```

## 無効化

作業を終えるときは、ターミナルで:

```bash
deactivate
```
