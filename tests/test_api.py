from app.api import examples, normalize_endpoint
from app.examples import FREE_TEXT_SAMPLE
from app.models import NormalizeRequest


def test_examples_endpoint_exposes_both_demo_inputs():
    response = examples()
    assert "Students enroll" in response["free_text"]
    assert "CREATE TABLE enrollment_report" in response["sql_ddl"]


def test_normalize_endpoint_runs_offline_text_demo():
    response = normalize_endpoint(NormalizeRequest(
        text=" ".join(FREE_TEXT_SAMPLE.split()),
        allow_demo_fallback=True,
        target_normal_form="3NF",
        verify=False,
    ))
    assert "CREATE TABLE students" in response.sql
    assert response.normalization.tables[0].name == "students"
    assert response.refinement_attempts == 0
