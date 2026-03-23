from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    db_path = (Path(__file__).resolve().parents[1] / "mentorseeker.db").as_posix()
    return f"sqlite:///{db_path}"


def _default_data_dir() -> str:
    return str((Path(__file__).resolve().parents[2] / "data").resolve())


class Settings(BaseSettings):
    app_name: str = "MentorSeeker API"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = Field(default_factory=_default_database_url)
    data_dir: str = Field(default_factory=_default_data_dir)

    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-5-mini"

    default_user_email: str = "demo@mentorseeker.local"
    default_user_name: str = "Demo User"

    model_config = SettingsConfigDict(
        env_file=str((Path(__file__).resolve().parents[1] / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def ensure_dirs(self) -> None:
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()
