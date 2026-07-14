"""Single source of truth for configuration. Tipada e validada via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: Literal["local", "staging", "production"] = "local"
    app_log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ---- Identidade do bot (persona) ----
    # Estes valores personalizam quem é o assistente SEM tocar em código.
    # Ajuste no .env para adaptar o template à sua empresa.
    bot_name: str = "Assistente"
    bot_company: str = "Sua Empresa"
    bot_description: str = (
        "atendimento ao cliente e informações institucionais"
    )
    bot_language: str = "PT-BR"
    # Caminho opcional para um arquivo de texto que SUBSTITUI todo o system prompt.
    # Vazio = usa o template padrão montado a partir dos campos acima.
    system_prompt_file: str = ""
    # Habilita a tool de exemplo de faturamento/ERP (ver src/chatbot/tools/sales.py).
    sales_tool_enabled: bool = True

    # ---- LLM ----
    google_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.2
    embedding_model: str = "gemini-embedding-001"

    # ---- Postgres ----
    postgres_user: str = "chatbot"
    postgres_password: str = "chatbot"
    postgres_db: str = "chatbot"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_async_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---- Redis ----
    redis_url: str = "redis://redis:6379/0"
    inbox_stream: str = "chatbot:inbox"
    inbox_group: str = "chatbot-workers"
    inbox_debounce_seconds: float = 2.0

    # ---- Qdrant ----
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "chatbot_kb"

    # ---- Reranker ----
    reranker: Literal["cohere", "off"] = "off"
    cohere_api_key: str = ""

    # ---- WAHA ----
    waha_base_url: str = "http://waha:3000"
    waha_api_key: str = ""
    waha_session: str = "default"
    webhook_public_url: str = "http://chatbot-api:8000/webhook/waha"
    # Números permitidos (separados por vírgula). Vazio = aceita todos.
    allowed_chat_ids: str = ""

    @property
    def allowed_numbers(self) -> set[str]:
        if not self.allowed_chat_ids:
            return set()
        return {n.strip() for n in self.allowed_chat_ids.split(",") if n.strip()}

    # ---- Sistema externo de exemplo (ERP / API de relatório) ----
    # Endpoint de exemplo consumido pela tool `buscar_faturamento_itens`.
    # Troque pela URL do SEU sistema (ou desabilite via SALES_TOOL_ENABLED=false).
    erp_sales_url: str = "https://api.exemplo.com/relatorio-de-vendas"
    # Nome do parâmetro/modo que sua API espera (ajuste ao seu contrato).
    erp_sales_mode: str = "vendas"

    # ---- Observabilidade ----
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
