from app.groq_config import DEFAULT_GROQ_MODEL, is_model_not_found, model_candidates, should_try_next_model


class ModelNotFoundError(Exception):
    status_code = 404


def test_default_model_is_current_fallback_safe_model():
    assert DEFAULT_GROQ_MODEL == "openai/gpt-oss-20b"


def test_model_candidates_keep_preferred_model_first_without_duplicates():
    candidates = model_candidates("llama-3.3-70b-versatile")
    assert candidates[0] == "llama-3.3-70b-versatile"
    assert candidates.count("openai/gpt-oss-20b") == 1


def test_model_not_found_detection_handles_sdk_status_code():
    assert is_model_not_found(ModelNotFoundError("missing model"))


def test_json_validation_error_moves_to_next_model():
    assert should_try_next_model(Exception("code: json_validate_failed"))
