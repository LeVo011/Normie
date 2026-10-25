"""LLM-backed extraction with Pydantic validation and a bounded repair retry."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from groq import Groq
from pydantic import ValidationError

from app.ddl_parser import parse_create_table
from app.examples import demo_extraction_for
from app.groq_config import DEFAULT_GROQ_MODEL, model_candidates, should_try_next_model
from app.input_layer import detect_input_kind
from app.models import ExtractionResult, InputKind, ParsedDDL


class ExtractionError(RuntimeError):
    pass


EXTRACTION_SYSTEM_PROMPT = """You are an expert relational database analyst.
Extract a conservative schema hypothesis from the supplied input. Return ONLY a JSON object.
Use exactly this shape:
{
  "input_kind": "free_text" | "sql_ddl",
  "entities": [{
    "name": "snake_case_relation_name",
    "attributes": [{"name": "snake_case_column", "data_type": "SQL type", "multi_valued": false, "nullable": true}],
    "candidate_primary_keys": [["column_name"]],
    "functional_dependencies": [{"determinant": ["x"], "dependent": ["y"], "explanation": "why"}]
  }],
  "assumptions": ["..."]
}
Only name attributes present in the DDL structure when one is supplied. Do not invent facts.
Functional dependencies must be plausible business rules, not merely column correlations."""


class ExtractionService:
    def __init__(self, model: str | None = None) -> None:
        load_dotenv()
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.api_key = os.getenv("GROQ_API_KEY")

    def _prompt(self, text: str, input_kind: InputKind, parsed: ParsedDDL | None) -> str:
        if parsed is None:
            return f"Input kind: {input_kind.value}\nDomain description:\n{text}"
        return "\n".join([
            "Input kind: sql_ddl",
            "Original SQL (for context only):",
            text,
            "Parsed DDL structure (these are the allowed columns):",
            json.dumps(parsed.model_dump(), indent=2),
        ])

    def extract(self, text: str, allow_demo_fallback: bool = False) -> ExtractionResult:
        input_kind = detect_input_kind(text)
        parsed = parse_create_table(text) if input_kind == InputKind.SQL_DDL else None
        if allow_demo_fallback:
            demo = demo_extraction_for(text, input_kind, parsed)
            if demo is not None:
                return demo
        if not self.api_key:
            raise ExtractionError("GROQ_API_KEY is not set. Add it to .env, or use one of the built-in demo samples.")
        prompt = self._prompt(text, input_kind, parsed)
        return self._extract_with_groq(prompt, parsed)

    def refine(self, text: str, prior_extraction: ExtractionResult, verifier_concerns: list[str]) -> ExtractionResult:
        """Re-extract after a verifier identifies concrete semantic concerns.

        The LLM may revise the extraction hypothesis, but the next normalization
        pass remains fully deterministic.
        """
        if not self.api_key:
            raise ExtractionError("Cannot refine without GROQ_API_KEY.")
        input_kind = detect_input_kind(text)
        parsed = parse_create_table(text) if input_kind == InputKind.SQL_DDL else None
        prompt = "\n\n".join([
            self._prompt(text, input_kind, parsed),
            "Prior extraction JSON:",
            prior_extraction.model_dump_json(indent=2),
            "Verifier concerns to address only when justified by the input:",
            json.dumps(verifier_concerns),
            "Return a revised extraction in the required JSON shape. Preserve valid facts and do not invent columns.",
        ])
        return self._extract_with_groq(prompt, parsed)

    def _extract_with_groq(self, prompt: str, parsed: ParsedDDL | None) -> ExtractionResult:
        client = Groq(api_key=self.api_key)
        last_error: Exception | None = None
        for attempt in range(2):
            repair = "" if attempt == 0 else (
                "\nYour prior output failed Pydantic validation. Return the exact JSON shape requested, "
                "with non-empty lists for entities and each FD determinant/dependent."
            )
            try:
                response = self._completion(client, prompt + repair)
                content = response.choices[0].message.content
                if not content:
                    raise ExtractionError("Groq returned an empty extraction response")
                extraction = ExtractionResult.model_validate_json(content)
                self._validate_ddl_columns(extraction, parsed)
                extraction.extraction_source = "groq"
                return extraction
            except (ValidationError, json.JSONDecodeError, ExtractionError) as error:
                last_error = error
            except Exception as error:  # SDK/API errors are retryable once for a live demo.
                last_error = error
        raise ExtractionError(f"Extraction failed after two attempts: {last_error}")

    def _completion(self, client: Groq, prompt: str):
        last_error: Exception | None = None
        for model in model_candidates(self.model):
            try:
                response = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                self.model = model
                return response
            except Exception as error:
                last_error = error
                if not should_try_next_model(error):
                    raise
        raise ExtractionError(f"No configured Groq model is available: {last_error}")

    @staticmethod
    def _validate_ddl_columns(extraction: ExtractionResult, parsed: ParsedDDL | None) -> None:
        if parsed is None:
            return
        allowed = {attribute.name for attribute in parsed.attributes}
        for entity in extraction.entities:
            used = {attribute.name for attribute in entity.attributes}
            if not used <= allowed:
                raise ExtractionError(f"LLM invented DDL columns: {sorted(used - allowed)}")
            for fd in entity.functional_dependencies:
                fd_attributes = set(fd.determinant) | set(fd.dependent)
                if not fd_attributes <= allowed:
                    raise ExtractionError(f"LLM emitted an FD with unknown columns: {sorted(fd_attributes - allowed)}")
