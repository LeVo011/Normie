"""Small, deliberately conservative CREATE TABLE parser backed by sqlparse."""

from __future__ import annotations

import re

import sqlparse

from app.models import AttributeSpec, ParsedDDL


CREATE_HEADER = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)\s*\(", re.IGNORECASE)


def _split_top_level(body: str) -> list[str]:
    parts, current, depth = [], [], 0
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _parenthesized_body(statement: str, start: int) -> str:
    depth = 0
    for index in range(start, len(statement)):
        if statement[index] == "(":
            depth += 1
        elif statement[index] == ")":
            depth -= 1
            if depth == 0:
                return statement[start + 1:index]
    raise ValueError("CREATE TABLE statement has an unclosed parenthesis")


def parse_create_table(sql: str) -> ParsedDDL:
    """Parse one CREATE TABLE statement and preserve the declared column types."""
    statements = sqlparse.parse(sql)
    create_statement = next((str(statement) for statement in statements if CREATE_HEADER.search(str(statement))), None)
    if create_statement is None:
        raise ValueError("No CREATE TABLE statement was found")
    match = CREATE_HEADER.search(create_statement)
    assert match is not None
    table_name = match.group(1).split(".")[-1].lower()
    open_paren = create_statement.find("(", match.start())
    body = _parenthesized_body(create_statement, open_paren)
    attributes: list[AttributeSpec] = []
    primary_key: list[str] = []
    for item in _split_top_level(body):
        item = item.strip()
        if not item:
            continue
        key_match = re.match(r"PRIMARY\s+KEY\s*\(([^)]+)\)", item, re.IGNORECASE)
        if key_match:
            primary_key = [value.strip().strip('`[]\"').lower() for value in key_match.group(1).split(",")]
            continue
        if re.match(r"(?:CONSTRAINT\s+\w+\s+)?(?:FOREIGN|UNIQUE|CHECK)\b", item, re.IGNORECASE):
            continue
        column_match = re.match(r"[`\[]?([a-zA-Z_]\w*)[`\]]?\s+(.+)$", item, re.DOTALL)
        if not column_match:
            continue
        name, remainder = column_match.groups()
        data_type = re.split(r"\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|DEFAULT|REFERENCES|CHECK)\b", remainder,
                             maxsplit=1, flags=re.IGNORECASE)[0].strip()
        inline_primary_key = bool(re.search(r"\bPRIMARY\s+KEY\b", remainder, re.IGNORECASE))
        attributes.append(AttributeSpec(
            name=name,
            data_type=data_type or "TEXT",
            nullable=not bool(re.search(r"\bNOT\s+NULL\b", remainder, re.IGNORECASE)),
        ))
        if inline_primary_key:
            primary_key.append(name.lower())
    if not attributes:
        raise ValueError("No columns could be parsed from CREATE TABLE")
    return ParsedDDL(table_name=table_name, attributes=attributes, declared_primary_key=primary_key)
