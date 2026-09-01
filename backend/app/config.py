import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# products.db chuẩn hoá về đúng 1 vị trí trong package agent_core, resolve tuyệt đối
# theo vị trí file (không phụ thuộc cwd khi chạy uvicorn / pytest).
_DEFAULT_AGENT_DB = os.path.join(_APP_DIR, "agent_core", "products.db")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AgentRouter exposes the OpenAI Chat Completions wire protocol at /v1.
    llm_base_url: str = "https://agentrouter.org/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    dataset_path: str = "../Dataset.xlsx"
    catalog_path: str = "./data/catalog.normalized.json"
    # Danh sách origin được phép gọi API (CORS), phân tách bằng dấu phẩy.
    frontend_origins: str = "http://localhost:5173"
    # DB SQLite của agent_core; đường dẫn tuyệt đối mặc định, override bằng AGENT_DB_PATH.
    agent_db_path: str = _DEFAULT_AGENT_DB
    # Nguồn Excel để rebuild DB (chỉ dùng khi chạy data_ingestion).
    excel_source_path: str = "../Spec_cate_gia.cleaned.xlsx"


@lru_cache
def get_settings() -> Settings:
    return Settings()
