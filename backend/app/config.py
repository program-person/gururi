from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="jr_route_", env_file=".env", extra="ignore")

    data_path: Path = Path(__file__).resolve().parent.parent / "data" / "graph.json"
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    extra_origins: list[str] = []

    @property
    def cors_origins(self) -> list[str]:
        return self.allowed_origins + self.extra_origins


settings = Settings()
