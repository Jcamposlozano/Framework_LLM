"""Pure, deterministic comparison; no provider calls or domain heuristics."""

from extracteval.application.verification import evidence_findings
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.specification import (
    CategoryValue,
    OperationalDictionary,
    SemanticValue,
    TextValue,
)
from extracteval.core.verification import (
    ComparisonRelation,
    ComparisonResult,
    ExtractionSnapshot,
    IndependentVerification,
    SemanticState,
    VariableComparison,
)


def normalize(
    value: SemanticValue | None,
    variable_id: str,
    dictionary: OperationalDictionary,
) -> tuple[object, tuple[str, ...]]:
    if value is None:
        return None, ()
    normalized = value.model_dump(mode="json")
    applied: list[str] = []
    if dictionary.clinically_approved and isinstance(value, CategoryValue | TextValue):
        text = value.value
        for rule_id in dictionary.variable(variable_id).normalization_rules:
            rule = next(r for r in dictionary.normalization if r.rule_id == rule_id)
            if not rule.approved:
                continue
            before = text
            if rule.operation == "strip":
                text = text.strip()
            elif rule.operation == "casefold":
                text = text.casefold()
            else:
                text = rule.aliases.get(text, text)
            if text != before:
                applied.append(rule_id)
        normalized["value"] = text
    return normalized, tuple(applied)


def original_state(extraction: ExtractionSnapshot, variable_id: str) -> SemanticState | None:
    result = next((r for r in extraction.results if r.trace.variable_id == variable_id), None)
    if result is None or result.technical_error is not None:
        return None
    if variable_id in extraction.semantic_states:
        return extraction.semantic_states[variable_id]
    if result.abstention:
        return SemanticState.ABSTAIN
    return SemanticState.VALUE if result.value is not None else SemanticState.NO_RESPONSE


def validate_inputs(
    extraction_a: ExtractionSnapshot,
    verification: IndependentVerification,
    dictionary: OperationalDictionary,
    document: Document | None,
) -> None:
    if extraction_a.document_id != verification.document_id:
        raise ValueError("Cannot compare different documents")
    if (
        extraction_a.dictionary != dictionary.artifact
        or verification.dictionary != dictionary.artifact
    ):
        raise ValueError("Cannot compare different dictionaries")
    if document is not None and (
        document.document_id != extraction_a.document_id
        or content_hash(document) != verification.document_hash
    ):
        raise ValueError("Verification document hash mismatch")
    for result in extraction_a.results:
        result.validate_against(dictionary)
    ids = [v.variable_id for v in verification.payload.variables]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate verification variables")
    for proposal in verification.payload.variables:
        definition = dictionary.variable(proposal.variable_id)
        if proposal.proposed_value is not None:
            definition.validate_value(proposal.proposed_value)


def compare_extractions(
    extraction_a: ExtractionSnapshot,
    independent_verification: IndependentVerification,
    dictionary: OperationalDictionary,
    document: Document | None = None,
) -> ComparisonResult:
    verification = independent_verification
    validate_inputs(extraction_a, verification, dictionary, document)
    originals = {r.trace.variable_id: r for r in extraction_a.results}
    proposals = {v.variable_id: v for v in verification.payload.variables}
    findings: dict[str, set[str]] = {v.variable_id: set() for v in dictionary.variables}
    # Consistency rules are declarative, external, and require explicit approval.
    for source, values in (
        ("a", {k: v.value for k, v in originals.items() if v.technical_error is None}),
        ("verifier", {k: v.proposed_value for k, v in proposals.items()}),
    ):
        for review_rule in dictionary.review_rules:
            if all(k in values and values[k] == v for k, v in review_rule.when.items()):
                mismatches = [
                    k for k, v in review_rule.expected.items() if k in values and values[k] != v
                ]
                if mismatches:
                    label = "inconsistency" if review_rule.approved else "potential_inconsistency"
                    for key in (*review_rule.when, *mismatches):
                        findings[key].add(source + ":" + label + ":" + review_rule.rule_id)
        if dictionary.clinically_approved:
            for rule in dictionary.consistency_rules:
                if rule.approved and all(values.get(k) == v for k, v in rule.when.items()):
                    if values.get(rule.conflicting_variable) == rule.conflicting_value:
                        for key in (*rule.when, rule.conflicting_variable):
                            findings[key].add(source + ":inconsistency:" + rule.rule_id)
    variables: list[VariableComparison] = []
    for definition in dictionary.variables:
        relation: ComparisonRelation
        key = definition.variable_id
        a, v = originals.get(key), proposals.get(key)
        flags = findings[key]
        rule_ids: tuple[str, ...] = ()
        if a is not None:
            checks = (
                evidence_findings(document, a.evidence.items)
                if document
                else (("evidence_unverifiable",) if a.evidence.items else ("evidence_missing",))
            )
            flags.update("a:" + code for code in checks)
            flags.update("a:" + f.code for f in a.findings)
        if v is not None:
            checks = (
                evidence_findings(document, v.evidence)
                if document
                else verification.evidence_findings.get(key, ("evidence_unverifiable",))
            )
            flags.update("verifier:" + code for code in checks)
            flags.update("verifier:uncertainty:" + flag for flag in v.uncertainty_flags)
            if v.requires_human_review:
                flags.add("verifier:human_review_requested")
        if verification.audit.error or (a is not None and a.technical_error):
            relation = "technical_error"
        elif (
            a is None
            or v is None
            or original_state(extraction_a, key) == SemanticState.NO_RESPONSE
            or v.semantic_state == SemanticState.NO_RESPONSE
        ):
            relation = "missing_response"
        elif a.value == v.proposed_value and original_state(extraction_a, key) == v.semantic_state:
            relation = "exact_match"
        else:
            left, lr = normalize(a.value, key, dictionary)
            right, rr = normalize(v.proposed_value, key, dictionary)
            if left == right and original_state(extraction_a, key) == v.semantic_state:
                relation = "normalization_difference"
                rule_ids = tuple(sorted(set(lr + rr)))
            else:
                relation = "value_difference"
        variables.append(
            VariableComparison(
                variable_id=key,
                relation=relation,
                findings=tuple(sorted(flags)),
                normalization_rule_ids=rule_ids,
            )
        )
    base_hash, verification_hash = content_hash(extraction_a), content_hash(verification)
    comparison_hash = content_hash(
        {
            "a": base_hash,
            "v": verification_hash,
            "dictionary": dictionary.model_dump(mode="json"),
            "variables": [v.model_dump(mode="json") for v in variables],
        }
    )
    return ComparisonResult(
        comparison_id="comparison-" + comparison_hash[:24],
        document_id=extraction_a.document_id,
        base_extraction_id=extraction_a.base_extraction_id,
        base_extraction_hash=base_hash,
        verification_id=verification.verification_id,
        verification_hash=verification_hash,
        dictionary=dictionary.artifact,
        variables=tuple(variables),
    )
