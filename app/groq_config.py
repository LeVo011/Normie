"""Resilient Groq model selection for accounts with different model access."""

from __future__ import annotations


DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
MODEL_FALLBACKS = ("openai/gpt-oss-20b", "qwen/qwen3.8-27b")


def model_candidates(preferred_model: str) -> list[str]:
    """Return the configured model followed by currently supported fallbacks."""
    return list(dict.fromkeys((preferred_model, *MODEL_FALLBACKS)))


def is_model_not_found(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    message = str(error).lower()
    return status_code == 404 or ("model" in message and ("does not exist" in message or "model_not_found" in message))


def should_try_next_model(error: Exception) -> bool:
    """Treat unavailable models and JSON-mode generation failures as model fallbacks."""
    message = str(error).lower()
    return is_model_not_found(error) or "json_validate_failed" in message or "failed to validate json" in message
