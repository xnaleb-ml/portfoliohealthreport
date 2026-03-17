from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Settings specifically for LLM and AI models."""

    # The API key is required. It will automatically look for ANTHROPIC_API_KEY in your environment.
    anthropic_api_key: str = Field(
        default=...,
        description="Anthropic API Key for Claude models",
        alias="ANTHROPIC_API_KEY",
    )

    # The default model to use for summarization and extraction.
    llm_model: str = Field(
        default="claude-sonnet-4-6",
        description="The default Anthropic model ID to use",
        alias="LLM_MODEL",
    )

    # Temperature (0.0 is best for analytical/extraction tasks to avoid hallucinations)
    default_llm_temperature: float = Field(
        default=0.0,
        description="Default temperature for LLM calls",
        alias="DEFAULT_LLM_TEMPERATURE",
    )

    # Max tokens for the output
    max_tokens_to_generate: int = Field(
        default=10000,
        description="Maximum tokens the model is allowed to generate for tool calls",
        alias="MAX_TOKENS_TO_GENERATE",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    """Main application settings that groups all sub-settings together."""

    # Instantiate the nested LLM settings
    llm: LLMSettings = Field(default_factory=LLMSettings)

    # Add other nested settings here later
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


def get_settings() -> Settings:
    """
    Returns a cached instance of the settings.
    Using lru_cache ensures we only read the .env file once during startup.
    """
    return Settings()
