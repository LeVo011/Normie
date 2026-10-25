from __future__ import annotations

import os
import json

from dotenv import load_dotenv
from groq import Groq
from pydantic import ValidationError

from app.models import NormalizationResult, VerificationResult
from app.groq_config import DEFAULT_GROQ_MODEL, model_candidates, should_try_next_model


VERIFY_PROMPT = """You are a cautious database schema reviewer. Review this normalized schema.
Return ONLY JSON with this exact shape:
{"approved": true, "concerns": ["..."], "relationship_suggestions": ["..."], "summary": "..."}
Set approved to false only for a concrete semantic issue that is supported by the original input and could be
addressed by revising the extracted entities, attributes, keys, or functional dependencies. Do not propose new
columns without clearly saying it is an assumption. Focus on semantic plausibility, missing relationships, and
obvious redundant fields. This is advisory: do not claim mathematical proof."""


class VerificationError(RuntimeError):
    pass


class VerifierService:
    def __init__(self, model: str | None = None) -> None:
        load_dotenv()
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.api_key = os.getenv("GROQ_API_KEY")

    def verify(self, normalization: NormalizationResult) -> VerificationResult:
        if not self.api_key:
            return VerificationResult(
                approved=True,
                summary="Verifier skipped because GROQ_API_KEY is not configured.",
            )
        client = Groq(api_key=self.api_key)
        last_error: Exception | None = None
        for attempt in range(2):
            repair = "" if attempt == 0 else "\nReturn valid JSON with every required field and correct value types."
            try:
                response = self._completion(client, normalization.model_dump_json(indent=2) + repair)
                content = response.choices[0].message.content
                if not content:
                    raise VerificationError("Groq returned an empty verifier response")
                return VerificationResult.model_validate_json(content)
            except (ValidationError, json.JSONDecodeError, VerificationError) as error:
                last_error = error
            except Exception as error:
                last_error = error
        raise VerificationError(f"Verification failed after two attempts: {last_error}")

    def _completion(self, client: Groq, prompt: str):
        last_error: Exception | None = None
        for model in model_candidates(self.model):
            try:
                response = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": VERIFY_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                self.model = model
                return response
            except Exception as error:
                last_error = error
                if not should_try_next_model(error):
                    raise
        raise VerificationError(f"No configured Groq model is available: {last_error}")
