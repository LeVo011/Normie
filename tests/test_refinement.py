from app.examples import enrollment_demo_extraction
from app.models import InputKind, VerificationResult
from app.pipeline import NormiePipeline


class RefiningExtractor:
    def __init__(self):
        self.refine_calls = 0

    def extract(self, text, allow_demo_fallback=False):
        return enrollment_demo_extraction(InputKind.FREE_TEXT)

    def refine(self, text, prior_extraction, verifier_concerns):
        self.refine_calls += 1
        return enrollment_demo_extraction(InputKind.FREE_TEXT)


class TwoPassVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, normalization):
        self.calls += 1
        if self.calls == 1:
            return VerificationResult(approved=False, concerns=["Confirm the course-to-instructor assumption."], summary="Review again.")
        return VerificationResult(approved=True, summary="Approved after refinement.")


def test_pipeline_runs_one_bounded_refinement_pass_when_verifier_flags_issue():
    pipeline = NormiePipeline()
    extractor = RefiningExtractor()
    verifier = TwoPassVerifier()
    pipeline.extractor = extractor
    pipeline.verifier = verifier

    result = pipeline.run("sample", verify=True, max_refinement_attempts=1)

    assert result.refinement_attempts == 1
    assert extractor.refine_calls == 1
    assert verifier.calls == 2
    assert result.verification.approved is True
