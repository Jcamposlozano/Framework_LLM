"""Explicit policy enforcement; a verifier proposal is never an expert reference."""

from extracteval.application.comparison import compare_extractions, original_state
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.specification import OperationalDictionary
from extracteval.core.verification import (
    ComparisonResult,
    DecisionAction,
    ExtractionSnapshot,
    IndependentVerification,
    ReconciledExtraction,
    ReconciliationDecision,
    ReconciliationPolicy,
    ReplacementRule,
    SemanticState,
    VariableVerification,
)


def _replacement_evidence_matches(
    rule: ReplacementRule,
    proposal: VariableVerification,
    document: Document,
    findings: tuple[str, ...],
) -> bool:
    problems = {finding for finding in findings if finding.startswith("verifier:")}
    if rule.evidence_scope is None:
        return not problems and all(
            any(quote in (item.quote or "") for item in proposal.evidence)
            for quote in rule.required_evidence_quotes
        )

    # Without declared sections, offsets still locate evidence in the original text.
    if not document.sections:
        problems.discard("verifier:evidence_section_missing")
    if problems or len(proposal.evidence) != 1 or document.text is None:
        return False
    item = proposal.evidence[0]
    if item.start is None or item.end is None or item.quote is None:
        return False
    if len(rule.required_evidence_quotes) != 1:
        return False
    if item.quote.casefold() != rule.required_evidence_quotes[0].casefold():
        return False
    before = document.text[: item.start]
    after = document.text[item.end :]
    left = before.rstrip(" \t")
    starts_sentence = (
        not left
        or left.endswith(("\n", "\r"))
        or (before[-1:].isspace() and left.endswith((".", "!", "?")))
    )
    return starts_sentence and (not after or after[0].isspace())


def reconcile(
    document: Document,
    extraction_a: ExtractionSnapshot,
    verification: IndependentVerification,
    comparison: ComparisonResult,
    policy: ReconciliationPolicy,
    dictionary: OperationalDictionary,
) -> ReconciledExtraction:
    # Reject stale, forged, or edited comparisons before applying any policy.
    if comparison != compare_extractions(extraction_a, verification, dictionary, document):
        raise ValueError("Comparison does not match the supplied inputs")
    before_hash = content_hash(extraction_a)
    originals = {r.trace.variable_id: r for r in extraction_a.results}
    proposals = {v.variable_id: v for v in verification.payload.variables}
    decisions: list[ReconciliationDecision] = []
    for item in comparison.variables:
        key = item.variable_id
        a, v = originals.get(key), proposals.get(key)
        old = a.value if a is not None else None
        old_state = original_state(extraction_a, key)
        new, state = old, old_state
        error = a.technical_error if a is not None else None
        rule_id = None
        review = False
        if item.relation == "exact_match" and not item.findings:
            action, reason = DecisionAction.KEEP_A, "documentary_agreement_only"
        else:
            review = True
            action = DecisionAction(policy.unresolved_action)
            reason = "unresolved_discrepancy"
            if not dictionary.clinically_approved:
                action, reason = DecisionAction.HUMAN_REVIEW, "dictionary_not_approved"
            # A technical failure stays operational, even under an ABSTAIN policy.
            if item.relation == "technical_error":
                action, reason = DecisionAction.HUMAN_REVIEW, "technical_failure"
            elif dictionary.clinically_approved and v is not None:
                for rule in policy.replacement_rules:
                    # Evidence problems on A alone do not disqualify a well-supported proposal.
                    consistency_problems = any("inconsistency:" in f for f in item.findings)
                    if (
                        rule.approved
                        and rule.variable_id == key
                        and rule.proposed_value == v.proposed_value
                        and rule.semantic_state == v.semantic_state
                        and rule.semantic_state
                        not in (SemanticState.NO_RESPONSE, SemanticState.ABSTAIN)
                        and set(rule.required_rule_ids) <= set(v.applied_rule_ids)
                        and set(v.applied_rule_ids) <= set(rule.required_rule_ids) | {rule.rule_id}
                        and rule.literal_evidence_sufficient
                        and rule.required_evidence_quotes
                        and v.evidence_type == "literal"
                        and v.evidence
                        and not v.uncertainty_flags
                        and not v.requires_human_review
                        and not consistency_problems
                        and (
                            rule.evidence_scope is None
                            or (old, old_state) != (v.proposed_value, v.semantic_state)
                        )
                        and _replacement_evidence_matches(rule, v, document, item.findings)
                    ):
                        dictionary.variable(key).validate_value(rule.proposed_value)
                        action, reason = (
                            DecisionAction.REPLACE_WITH_VERIFIED,
                            "approved_replacement_rule",
                        )
                        new, state, rule_id = v.proposed_value, v.semantic_state, rule.rule_id
                        error, review = None, False
                        break
            if action == DecisionAction.ABSTAIN:
                new, state = None, SemanticState.ABSTAIN
        decisions.append(
            ReconciliationDecision(
                variable_id=key,
                action=action,
                reason=reason,
                rule_id=rule_id,
                previous_value=old,
                resulting_value=new,
                previous_state=old_state,
                resulting_state=state,
                technical_error=error,
                requires_human_review=review,
            )
        )
    if before_hash != content_hash(extraction_a):
        raise RuntimeError("Original extraction mutated during reconciliation")
    reconciliation_hash = content_hash(
        {"comparison": content_hash(comparison), "policy": policy.model_dump(mode="json")}
    )
    return ReconciledExtraction(
        reconciliation_id="reconciliation-" + reconciliation_hash[:24],
        document_id=document.document_id,
        document_hash=content_hash(document),
        base_extraction_id=extraction_a.base_extraction_id,
        base_extraction_hash=before_hash,
        source_sha256=extraction_a.source_sha256,
        verification_id=verification.verification_id,
        comparison_id=comparison.comparison_id,
        dictionary=dictionary.artifact,
        policy_version=policy.version,
        decisions=tuple(decisions),
        auxiliary=extraction_a.model_copy(deep=True).auxiliary,
    )
