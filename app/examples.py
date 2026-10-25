from __future__ import annotations

from app.models import AttributeSpec, EntitySpec, ExtractionResult, FunctionalDependency, InputKind, ParsedDDL


FREE_TEXT_SAMPLE = """Students enroll in courses each semester. A student has a name and email.
Each course has a title and is taught by one instructor. An instructor has a name.
For each student, course, and semester, store the final grade."""

MESSY_SQL_SAMPLE = """CREATE TABLE enrollment_report (
    student_id INTEGER NOT NULL,
    student_name VARCHAR(100) NOT NULL,
    student_email VARCHAR(255) NOT NULL,
    course_id INTEGER NOT NULL,
    course_title VARCHAR(200) NOT NULL,
    instructor_id INTEGER NOT NULL,
    instructor_name VARCHAR(100) NOT NULL,
    semester VARCHAR(20) NOT NULL,
    grade CHAR(2),
    PRIMARY KEY (student_id, course_id, semester)
);

INSERT INTO enrollment_report VALUES
    (1, 'Asha', 'asha@example.edu', 101, 'Advanced SQL', 7, 'Dr Rao', 'Fall 2026', 'A');"""


def enrollment_demo_extraction(input_kind: InputKind, parsed_ddl: ParsedDDL | None = None) -> ExtractionResult:
    defaults = {
        "student_id": "INTEGER", "student_name": "VARCHAR(100)", "student_email": "VARCHAR(255)",
        "course_id": "INTEGER", "course_title": "VARCHAR(200)", "instructor_id": "INTEGER",
        "instructor_name": "VARCHAR(100)", "semester": "VARCHAR(20)", "grade": "CHAR(2)",
    }
    if parsed_ddl:
        attributes = parsed_ddl.attributes
        name = parsed_ddl.table_name
        key = parsed_ddl.declared_primary_key or ["student_id", "course_id", "semester"]
    else:
        attributes = [AttributeSpec(name=name, data_type=data_type) for name, data_type in defaults.items()]
        name = "enrollment_record"
        key = ["student_id", "course_id", "semester"]
    return ExtractionResult(
        input_kind=input_kind,
        extraction_source="demo",
        entities=[EntitySpec(
            name=name,
            attributes=attributes,
            candidate_primary_keys=[key],
            functional_dependencies=[
                FunctionalDependency(determinant=["student_id"], dependent=["student_name", "student_email"],
                                     explanation="A student ID identifies the student's facts."),
                FunctionalDependency(determinant=["course_id"], dependent=["course_title", "instructor_id"],
                                     explanation="A course ID identifies its title and assigned instructor."),
                FunctionalDependency(determinant=["instructor_id"], dependent=["instructor_name"],
                                     explanation="An instructor ID identifies the instructor's name."),
                FunctionalDependency(determinant=["student_id", "course_id", "semester"], dependent=["grade"],
                                     explanation="Grade is specific to one enrollment in one semester."),
            ],
        )],
        assumptions=["A course has one assigned instructor for this prototype.",
                     "The enrollment key is student_id, course_id, semester."],
    )


def demo_extraction_for(text: str, input_kind: InputKind, parsed_ddl: ParsedDDL | None = None) -> ExtractionResult | None:
    # Swagger editors commonly collapse or alter line breaks. Normalizing
    # whitespace keeps the offline demo stable without broadening it to arbitrary prose.
    normalized_text = " ".join(text.split())
    normalized_sample = " ".join(FREE_TEXT_SAMPLE.split())
    if input_kind == InputKind.FREE_TEXT and normalized_text == normalized_sample:
        return enrollment_demo_extraction(input_kind)
    if input_kind == InputKind.SQL_DDL and parsed_ddl and parsed_ddl.table_name == "enrollment_report":
        columns = {attribute.name for attribute in parsed_ddl.attributes}
        if {"student_id", "course_id", "semester", "grade"} <= columns:
            return enrollment_demo_extraction(input_kind, parsed_ddl)
    return None
