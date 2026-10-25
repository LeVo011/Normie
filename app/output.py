from __future__ import annotations

from app.models import NormalizationResult, TableSchema


def _column_sql(column) -> str:
    pieces = [f"    {column.name} {column.data_type}"]
    if not column.nullable:
        pieces.append("NOT NULL")
    return " ".join(pieces)


def create_table_sql(table: TableSchema) -> str:
    lines = [_column_sql(column) for column in table.columns]
    lines.append(f"    PRIMARY KEY ({', '.join(table.primary_key)})")
    for foreign_key in table.foreign_keys:
        lines.append(
            f"    FOREIGN KEY ({', '.join(foreign_key.columns)}) "
            f"REFERENCES {foreign_key.references_table} ({', '.join(foreign_key.references_columns)})"
        )
    return f"CREATE TABLE {table.name} (\n" + ",\n".join(lines) + "\n);"


def render_sql(normalization: NormalizationResult) -> str:
    return "\n\n".join(create_table_sql(table) for table in normalization.tables)


def render_report(normalization: NormalizationResult) -> str:
    lines = [f"Normalization target: {normalization.target_normal_form}."]
    for entity in normalization.entities:
        keys = " or ".join("(" + ", ".join(key) + ")" for key in entity.candidate_keys)
        lines.append(f"For {entity.entity}, detected candidate key(s): {keys}.")
        if not entity.findings:
            lines.append(f"{entity.entity} needed no decomposition based on the supplied dependencies.")
        for finding in entity.findings:
            lines.append(f"[{finding.normal_form}] {finding.message}")
        tables = ", ".join(table.name for table in entity.tables)
        lines.append(f"Split {entity.entity} into: {tables}.")
        for table in entity.tables:
            details = ", ".join(column.name for column in table.columns)
            lines.append(f"- {table.name} stores: {details}; primary key: ({', '.join(table.primary_key)}).")
    return "\n".join(lines)


def render_mermaid_erd(normalization: NormalizationResult) -> str:
    """Render a portable text ERD that can be pasted into Mermaid Live Editor."""
    lines = ["erDiagram"]
    for table in normalization.tables:
        lines.append(f"  {table.name} {{")
        primary = set(table.primary_key)
        foreign = {column for fk in table.foreign_keys for column in fk.columns}
        for column in table.columns:
            markers = []
            if column.name in primary:
                markers.append("PK")
            if column.name in foreign:
                markers.append("FK")
            suffix = f' "{", ".join(markers)}"' if markers else ""
            lines.append(f"    {column.data_type} {column.name}{suffix}")
        lines.append("  }")
    emitted: set[tuple[str, str, tuple[str, ...]]] = set()
    for child in normalization.tables:
        for foreign_key in child.foreign_keys:
            relationship = (foreign_key.references_table, child.name, tuple(foreign_key.columns))
            if relationship not in emitted:
                lines.append(f"  {foreign_key.references_table} ||--o{{ {child.name} : references")
                emitted.add(relationship)
    return "\n".join(lines)
