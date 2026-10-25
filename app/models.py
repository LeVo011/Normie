from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class InputKind(str, Enum):
    FREE_TEXT = "free_text"
    SQL_DDL = "sql_ddl"


class AttributeSpec(BaseModel):
    name: str
    data_type: str = "TEXT"
    multi_valued: bool = False
    nullable: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()


class FunctionalDependency(BaseModel):
    determinant: list[str] = Field(min_length=1)
    dependent: list[str] = Field(min_length=1)
    explanation: str = ""

    @field_validator("determinant", "dependent")
    @classmethod
    def normalize_attributes(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
        if not cleaned:
            raise ValueError("An FD side cannot be empty")
        return cleaned


class EntitySpec(BaseModel):
    name: str
    attributes: list[AttributeSpec] = Field(min_length=1)
    candidate_primary_keys: list[list[str]] = Field(default_factory=list)
    functional_dependencies: list[FunctionalDependency] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_entity_name(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class ExtractionResult(BaseModel):
    input_kind: InputKind
    entities: list[EntitySpec] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    extraction_source: Literal["groq", "demo"] = "groq"


class ParsedDDL(BaseModel):
    table_name: str
    attributes: list[AttributeSpec]
    declared_primary_key: list[str] = Field(default_factory=list)


class ForeignKey(BaseModel):
    columns: list[str]
    references_table: str
    references_columns: list[str]


class TableSchema(BaseModel):
    name: str
    columns: list[AttributeSpec]
    primary_key: list[str]
    foreign_keys: list[ForeignKey] = Field(default_factory=list)


class NormalizationFinding(BaseModel):
    normal_form: Literal["1NF", "2NF", "3NF", "BCNF"]
    relation: str
    message: str
    fd: FunctionalDependency | None = None


class EntityNormalization(BaseModel):
    entity: str
    candidate_keys: list[list[str]]
    findings: list[NormalizationFinding]
    tables: list[TableSchema]


class NormalizationResult(BaseModel):
    target_normal_form: Literal["3NF", "BCNF"]
    entities: list[EntityNormalization]
    tables: list[TableSchema]


class VerificationResult(BaseModel):
    approved: bool
    concerns: list[str] = Field(default_factory=list)
    relationship_suggestions: list[str] = Field(default_factory=list)
    summary: str = ""


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)
    allow_demo_fallback: bool = False

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "text": (
                    "Students enroll in courses each semester. A student has a name and email. "
                    "Each course has a title and is taught by one instructor. An instructor has a name. "
                    "For each student, course, and semester, store the final grade."
                ),
                "allow_demo_fallback": True,
            }]
        }
    }


class NormalizeRequest(AnalyzeRequest):
    target_normal_form: Literal["3NF", "BCNF"] = "3NF"
    verify: bool = False
    max_refinement_attempts: int = Field(default=1, ge=0, le=2)

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "text": (
                    "Students enroll in courses each semester. A student has a name and email. "
                    "Each course has a title and is taught by one instructor. An instructor has a name. "
                    "For each student, course, and semester, store the final grade."
                ),
                "allow_demo_fallback": True,
                "target_normal_form": "3NF",
                "verify": False,
                "max_refinement_attempts": 1,
            }]
        }
    }


class PipelineResult(BaseModel):
    input_kind: InputKind
    extraction: ExtractionResult
    normalization: NormalizationResult
    sql: str
    report: str
    erd: str
    verification: VerificationResult | None = None
    refinement_attempts: int = 0
