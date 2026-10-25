"""Deterministic functional-dependency algorithms used by Normie.

No network or LLM calls are made in this module.  The extraction stage may be
uncertain; once it supplies an FD set, every result below is reproducible.
"""

from __future__ import annotations

from itertools import combinations
import re

from app.models import (
    AttributeSpec,
    EntityNormalization,
    EntitySpec,
    ForeignKey,
    FunctionalDependency,
    NormalizationFinding,
    NormalizationResult,
    TableSchema,
)


AttributeSet = frozenset[str]


def _fd(left: AttributeSet, right: AttributeSet, explanation: str = "") -> FunctionalDependency:
    return FunctionalDependency(determinant=sorted(left), dependent=sorted(right), explanation=explanation)


def _as_sets(fds: list[FunctionalDependency]) -> list[tuple[AttributeSet, AttributeSet, str]]:
    return [(frozenset(fd.determinant), frozenset(fd.dependent), fd.explanation) for fd in fds]


def attribute_closure(seed: set[str] | frozenset[str], fds: list[FunctionalDependency]) -> set[str]:
    """Return X+ by repeatedly applying every FD whose left side is known."""
    closure = set(seed)
    changed = True
    while changed:
        changed = False
        for left, right, _ in _as_sets(fds):
            if left <= closure and not right <= closure:
                closure.update(right)
                changed = True
    return closure


def candidate_keys(attributes: set[str], fds: list[FunctionalDependency]) -> list[set[str]]:
    """Enumerate minimal superkeys, ordered by cardinality then name."""
    if not attributes:
        return []
    rhs = set().union(*(set(fd.dependent) for fd in fds), set())
    required = attributes - rhs  # Cannot be derived, so every key must contain it.
    optional = sorted(attributes - required)
    keys: list[set[str]] = []
    for size in range(len(optional) + 1):
        for extra in combinations(optional, size):
            possible_key = required | set(extra)
            if any(existing <= possible_key for existing in keys):
                continue
            if attribute_closure(possible_key, fds) >= attributes:
                keys.append(possible_key)
    return keys


def minimal_cover(fds: list[FunctionalDependency]) -> list[FunctionalDependency]:
    """Compute a canonical cover: singleton RHS, minimal LHS, redundant FDs removed."""
    cover = [_fd(frozenset(fd.determinant), frozenset({item}), fd.explanation)
             for fd in fds for item in fd.dependent if item not in fd.determinant]

    index = 0
    while index < len(cover):
        left = set(cover[index].determinant)
        right = cover[index].dependent[0]
        for attribute in list(left):
            trial_left = left - {attribute}
            trial = cover[:index] + cover[index + 1:]
            if right in attribute_closure(trial_left, trial):
                left = trial_left
        cover[index] = _fd(frozenset(left), frozenset({right}), cover[index].explanation)
        index += 1

    index = 0
    while index < len(cover):
        fd = cover[index]
        without_current = cover[:index] + cover[index + 1:]
        if fd.dependent[0] in attribute_closure(set(fd.determinant), without_current):
            cover.pop(index)
        else:
            index += 1
    return cover


def _projected_fds(relation: set[str], fds: list[FunctionalDependency]) -> list[FunctionalDependency]:
    """Use FDs already known inside a relation; enough for synthesis/BCNF checks here."""
    return [fd for fd in minimal_cover(fds)
            if set(fd.determinant) <= relation and set(fd.dependent) <= relation]


def _is_superkey(determinant: set[str], relation: set[str], fds: list[FunctionalDependency]) -> bool:
    return attribute_closure(determinant, _projected_fds(relation, fds)) >= relation


def _three_nf_relations(attributes: set[str], fds: list[FunctionalDependency], keys: list[set[str]]) -> list[set[str]]:
    cover = minimal_cover(fds)
    # The canonical cover has a singleton RHS, but FDs sharing X belong in the
    # same synthesized relation X union {A, B, ...}.  This keeps dimensions
    # such as Students(student_id, student_name, student_email) together.
    grouped: dict[frozenset[str], set[str]] = {}
    for fd in cover:
        determinant = frozenset(fd.determinant)
        grouped.setdefault(determinant, set(determinant)).update(fd.dependent)
    relations: list[set[str]] = []
    for relation in grouped.values():
        if relation not in relations:
            relations.append(relation)
    if not any(any(key <= relation for key in keys) for relation in relations):
        relations.append(set(keys[0] if keys else attributes))
    # A subset relation adds no information after synthesis.
    return [relation for relation in relations if not any(relation < other for other in relations)]


def _bcnf_relations(attributes: set[str], fds: list[FunctionalDependency]) -> list[set[str]]:
    pending = [set(attributes)]
    finished: list[set[str]] = []
    while pending:
        relation = pending.pop()
        violation = next(
            (fd for fd in _projected_fds(relation, fds)
             if not _is_superkey(set(fd.determinant), relation, fds)),
            None,
        )
        if violation is None:
            finished.append(relation)
            continue
        left, right = set(violation.determinant), set(violation.dependent)
        first = left | right
        second = relation - (right - left)
        pending.extend([first, second])
    return finished


def _safe_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value or "relation"


def _relation_name(entity: str, relation: set[str], original_key: list[str], local_key: list[str], ordinal: int) -> str:
    """Name dimensions after their identifier; retain the source name for the key relation."""
    if set(original_key) <= relation:
        return _safe_name(entity)
    if len(local_key) == 1 and local_key[0].endswith("_id"):
        return _safe_name(local_key[0][:-3]) + "s"
    return f"{_safe_name(entity)}_{ordinal + 1}"


def _relation_key(relation: set[str], fds: list[FunctionalDependency], fallback: list[str]) -> list[str]:
    keys = candidate_keys(relation, _projected_fds(relation, fds))
    if keys:
        return sorted(keys[0])
    retained = [column for column in fallback if column in relation]
    return retained or [sorted(relation)[0]]


def _findings(entity: EntitySpec, keys: list[set[str]]) -> list[NormalizationFinding]:
    attributes = {attribute.name for attribute in entity.attributes}
    prime = set().union(*keys) if keys else set()
    findings: list[NormalizationFinding] = []
    for attribute in entity.attributes:
        if attribute.multi_valued:
            findings.append(NormalizationFinding(
                normal_form="1NF", relation=entity.name,
                message=f"{attribute.name} is multi-valued and must be stored in its own relation.",
            ))
    for fd in minimal_cover(entity.functional_dependencies):
        left, right = set(fd.determinant), set(fd.dependent)
        partial = any(left < key and any(item not in prime for item in right) for key in keys if len(key) > 1)
        if partial:
            findings.append(NormalizationFinding(
                normal_form="2NF", relation=entity.name,
                message=f"{', '.join(fd.dependent)} depends on part of a composite candidate key.", fd=fd,
            ))
        if not _is_superkey(left, attributes, entity.functional_dependencies) and any(item not in prime for item in right):
            findings.append(NormalizationFinding(
                normal_form="3NF", relation=entity.name,
                message=f"{', '.join(fd.determinant)} -> {', '.join(fd.dependent)} violates 3NF because the determinant is not a superkey.", fd=fd,
            ))
            findings.append(NormalizationFinding(
                normal_form="BCNF", relation=entity.name,
                message=f"{', '.join(fd.determinant)} is not a superkey, so this FD also violates BCNF.", fd=fd,
            ))
    return findings


def _make_foreign_keys(tables: list[TableSchema]) -> list[TableSchema]:
    for child in tables:
        foreign_keys: list[ForeignKey] = []
        child_columns = {column.name for column in child.columns}
        for parent in tables:
            if child.name == parent.name or not parent.primary_key:
                continue
            parent_key = set(parent.primary_key)
            if parent_key <= child_columns and parent_key != set(child.primary_key):
                foreign_keys.append(ForeignKey(
                    columns=parent.primary_key,
                    references_table=parent.name,
                    references_columns=parent.primary_key,
                ))
        child.foreign_keys = foreign_keys
    return tables


def normalize_entity(entity: EntitySpec, target_normal_form: str = "3NF") -> EntityNormalization:
    attributes = {attribute.name for attribute in entity.attributes}
    fds = [fd for fd in entity.functional_dependencies
           if set(fd.determinant) <= attributes and set(fd.dependent) <= attributes]
    keys = candidate_keys(attributes, fds)
    if not keys:
        keys = [attributes]
    relations = (_bcnf_relations(attributes, fds) if target_normal_form == "BCNF"
                 else _three_nf_relations(attributes, fds, keys))
    attribute_lookup = {attribute.name: attribute for attribute in entity.attributes}
    base_key = sorted(keys[0])
    tables: list[TableSchema] = []
    used_names: set[str] = set()
    for ordinal, relation in enumerate(relations):
        table_key = _relation_key(relation, fds, base_key)
        name = _relation_name(entity.name, relation, base_key, table_key, ordinal)
        while name in used_names:
            name = f"{name}_{ordinal + 1}"
        used_names.add(name)
        tables.append(TableSchema(
            name=name,
            columns=[attribute_lookup[column] for column in sorted(relation)],
            primary_key=table_key,
        ))
    # A 1NF violation becomes an owner-key/value table in addition to the FD decomposition.
    for attribute in entity.attributes:
        if attribute.multi_valued:
            name = f"{_safe_name(entity.name)}_{attribute.name}"
            owner_columns = [attribute_lookup[column] for column in base_key]
            tables.append(TableSchema(
                name=name,
                columns=owner_columns + [attribute],
                primary_key=base_key + [attribute.name],
            ))
    tables = _make_foreign_keys(tables)
    return EntityNormalization(
        entity=entity.name,
        candidate_keys=[sorted(key) for key in keys],
        findings=_findings(entity, keys),
        tables=tables,
    )


def normalize(extraction, target_normal_form: str = "3NF") -> NormalizationResult:
    entity_results = [normalize_entity(entity, target_normal_form) for entity in extraction.entities]
    return NormalizationResult(
        target_normal_form=target_normal_form,
        entities=entity_results,
        tables=[table for result in entity_results for table in result.tables],
    )
