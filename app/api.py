from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.extraction import ExtractionError
from app.examples import FREE_TEXT_SAMPLE, MESSY_SQL_SAMPLE
from app.models import AnalyzeRequest, NormalizeRequest, PipelineResult
from app.pipeline import NormiePipeline


app = FastAPI(title="Normie", version="0.1.0", description="AI-assisted, deterministic schema normalization.")
pipeline = NormiePipeline()
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _run(request: NormalizeRequest) -> PipelineResult:
    try:
        return pipeline.run(
            request.text,
            target_normal_form=request.target_normal_form,
            verify=request.verify,
            allow_demo_fallback=request.allow_demo_fallback,
            max_refinement_attempts=request.max_refinement_attempts,
        )
    except (ExtractionError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Upstream extraction/verifier error: {error}") from error


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "groq_configured": bool(pipeline.extractor.api_key),
        "model": pipeline.extractor.model,
    }


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api")
def api_index() -> dict[str, str]:
    return {
        "name": "Normie API",
        "status": "running",
        "documentation": "/docs",
        "health": "/health",
        "examples": "/examples",
        "web_app": "/",
        "analyze": "POST /analyze",
        "normalize": "POST /normalize",
        "report": "POST /report",
    }


@app.get("/examples")
def examples() -> dict[str, str]:
    """Return offline-safe examples for a live demo without a Groq API key."""
    return {
        "free_text": FREE_TEXT_SAMPLE,
        "sql_ddl": MESSY_SQL_SAMPLE,
        "usage": "Send either value to POST /normalize with allow_demo_fallback set to true.",
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    """Run input detection and extraction only, useful for inspecting LLM assumptions."""
    try:
        extraction = pipeline.extractor.extract(request.text, request.allow_demo_fallback)
        return {"input_kind": extraction.input_kind, "extraction": extraction}
    except (ExtractionError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/normalize", response_model=PipelineResult)
def normalize_endpoint(request: NormalizeRequest) -> PipelineResult:
    return _run(request)


@app.post("/report")
def report(request: NormalizeRequest) -> dict[str, str]:
    result = _run(request)
    return {"sql": result.sql, "report": result.report, "erd": result.erd}
