from app.examples import enrollment_demo_extraction
from app.examples import FREE_TEXT_SAMPLE, MESSY_SQL_SAMPLE, demo_extraction_for
from app.ddl_parser import parse_create_table
from app.models import AttributeSpec, EntitySpec, FunctionalDependency, InputKind
from app.normalization import attribute_closure, candidate_keys, normalize_entity
from app.pipeline import NormiePipeline


def test_attribute_closure_reaches_transitive_attributes():
    fds = [
        FunctionalDependency(determinant=["a"], dependent=["b"]),
        FunctionalDependency(determinant=["b"], dependent=["c"]),
    ]
    assert attribute_closure({"a"}, fds) == {"a", "b", "c"}


def test_candidate_key_detection_returns_minimal_keys():
    fds = [
        FunctionalDependency(determinant=["a"], dependent=["b"]),
        FunctionalDependency(determinant=["b"], dependent=["a"]),
        FunctionalDependency(determinant=["a"], dependent=["c"]),
    ]
    assert candidate_keys({"a", "b", "c"}, fds) == [{"a"}, {"b"}]


def test_three_nf_synthesis_splits_enrollment_demo():
    entity = enrollment_demo_extraction(InputKind.FREE_TEXT).entities[0]
    result = normalize_entity(entity)
    relation_columns = {frozenset(column.name for column in table.columns) for table in result.tables}
    assert frozenset({"student_id", "student_name", "student_email"}) in relation_columns
    assert frozenset({"course_id", "course_title", "instructor_id"}) in relation_columns
    assert frozenset({"instructor_id", "instructor_name"}) in relation_columns
    assert frozenset({"student_id", "course_id", "semester", "grade"}) in relation_columns
    assert any(finding.normal_form == "2NF" for finding in result.findings)
    assert {table.name for table in result.tables} == {"students", "courses", "instructors", "enrollment_record"}


def test_multivalued_attribute_is_moved_to_its_own_relation():
    entity = EntitySpec(
        name="student",
        attributes=[AttributeSpec(name="student_id"), AttributeSpec(name="phone_numbers", multi_valued=True)],
        functional_dependencies=[FunctionalDependency(determinant=["student_id"], dependent=["phone_numbers"])],
    )
    result = normalize_entity(entity)
    assert any(table.name == "student_phone_numbers" for table in result.tables)
    assert any(finding.normal_form == "1NF" for finding in result.findings)


def test_demo_fallback_tolerates_whitespace_changes():
    one_line_sample = " ".join(FREE_TEXT_SAMPLE.split())
    extraction = demo_extraction_for(one_line_sample, InputKind.FREE_TEXT)
    assert extraction is not None
    assert extraction.entities[0].name == "enrollment_record"


def test_sql_demo_parses_columns_and_preserves_data_types():
    parsed = parse_create_table(MESSY_SQL_SAMPLE)
    extraction = demo_extraction_for(MESSY_SQL_SAMPLE, InputKind.SQL_DDL, parsed)
    assert parsed.declared_primary_key == ["student_id", "course_id", "semester"]
    assert extraction is not None
    assert next(attribute for attribute in extraction.entities[0].attributes if attribute.name == "grade").data_type == "CHAR(2)"


def test_pipeline_generates_sql_report_and_erd_for_demo():
    result = NormiePipeline().run(FREE_TEXT_SAMPLE, allow_demo_fallback=True)
    assert "CREATE TABLE students" in result.sql
    assert "CREATE TABLE enrollment_record" in result.sql
    assert "Split enrollment_record into" in result.report
    assert "erDiagram" in result.erd
