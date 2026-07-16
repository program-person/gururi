from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="jr_route_", env_file=".env", extra="ignore")

    data_path: Path = Path(__file__).resolve().parent.parent / "data" / "graph.json"
    transit_map_path: Path = (
        Path(__file__).resolve().parent.parent / "data" / "transit_station_map.json"
    )
    # 本番はフロントの Next.js リライト（サーバー側プロキシ）経由で叩くため
    # ブラウザ向け CORS は原則不要。直接 API を公開したい場合のみ
    # JR_ROUTE_ALLOWED_ORIGINS で追加するか JR_ROUTE_ALLOW_ALL_ORIGINS=true にする
    allow_all_origins: bool = False
    allowed_origins: list[str] = ["http://localhost:3000"]

    # 探索系・外部API系エンドポイントのレート制限（IP単位・スライディングウィンドウ）
    rate_limit_enabled: bool = True
    rate_limit_max_requests: int = 30
    rate_limit_window_secs: float = 60.0


settings = Settings()
