from __future__ import annotations

from app.extraction import ExtractionService
from app.input_layer import detect_input_kind
from app.models import PipelineResult
from app.normalization import normalize
from app.output import render_mermaid_erd, render_report, render_sql
from app.verifier import VerifierService


class NormiePipeline:
    def __init__(self) -> None:
        self.extractor = ExtractionService()
        self.verifier = VerifierService()

    def run(self, text: str, target_normal_form: str = "3NF", verify: bool = False,
            allow_demo_fallback: bool = False, max_refinement_attempts: int = 1) -> PipelineResult:
        extraction = self.extractor.extract(text, allow_demo_fallback=allow_demo_fallback)
        normalization = normalize(extraction, target_normal_form)
        verification = None
        refinement_attempts = 0
        if verify:
            for _ in range(max_refinement_attempts + 1):
                verification = self.verifier.verify(normalization)
                if verification.approved or refinement_attempts >= max_refinement_attempts:
                    break
                extraction = self.extractor.refine(text, extraction, verification.concerns)
                normalization = normalize(extraction, target_normal_form)
                refinement_attempts += 1
        return PipelineResult(
            input_kind=detect_input_kind(text), extraction=extraction, normalization=normalization,
            sql=render_sql(normalization),
            report=render_report(normalization),
            erd=render_mermaid_erd(normalization),
            verification=verification,
            refinement_attempts=refinement_attempts,
        )
