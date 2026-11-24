"""Deterministic, non-semantic measurements of local documents."""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from hashlib import sha256
from math import ceil, isfinite
from statistics import NormalDist, median, quantiles

from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash

METHOD_VERSION = "1.0"
_WORD = re.compile(r"[^\W_]+")
_SENTENCE = re.compile(r"[.!?。！？]+|\n+")
_PARAGRAPH = re.compile(r"\n[^\S\n]*\n(?:[^\S\n]*\n)*")
_LIST_LINE = re.compile(r"^\s*(?:[-*•▪‣]|\d+[.)]|[A-Za-z][.)])\s+\S")
_NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*")
_DATE = re.compile(r"(?<!\d)(?:\d{4}([./-])\d{1,2}\1\d{1,2}|\d{1,2}([./-])\d{1,2}\2\d{2,4})(?!\d)")
_TIME = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)")
_PUNCTUATION = ".,;:!?¿¡()[]{}'\"«»-—/…"


def _words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text).casefold()
    return [word for word in _WORD.findall(normalized) if any(map(str.isalpha, word))]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mattr(words: list[str], window: int) -> float | None:
    if len(words) < window:
        return None
    counts = Counter(words[:window])
    distinct = len(counts)
    for index in range(window, len(words)):
        departing = words[index - window]
        counts[departing] -= 1
        if not counts[departing]:
            del counts[departing]
        counts[words[index]] += 1
        distinct += len(counts)
    return distinct / (window * (len(words) - window + 1))


def _text_metrics(text: str, window: int) -> dict[str, int | float | None]:
    words = _words(text)
    counts = Counter(words)
    word_count = len(words)
    lengths = [len(word) for word in words]
    lines = text.splitlines()
    layout = "\n".join(lines)
    sentence_lengths = [
        count for sentence in _SENTENCE.split(layout) if (count := len(_words(sentence)))
    ]
    characters = len(text)
    letters = sum(map(str.isalpha, text))
    numeric = sum(map(str.isnumeric, text))
    special = sum(unicodedata.category(char)[0] in "PS" for char in text)
    cased = sum(char.isupper() or char.islower() or char.istitle() for char in text)
    return {
        "characters": characters,
        "non_whitespace_characters": sum(not char.isspace() for char in text),
        "words": word_count,
        "unique_words": len(counts),
        "mean_word_length": _ratio(sum(lengths), word_count),
        "median_word_length": median(lengths) if lengths else None,
        "max_word_length": max(lengths, default=None),
        "lines": len(lines),
        "paragraphs": sum(bool(part.strip()) for part in _PARAGRAPH.split(layout)),
        "estimated_sentences": len(sentence_lengths),
        "mean_sentence_words": _ratio(sum(sentence_lengths), len(sentence_lengths)),
        "max_sentence_words": max(sentence_lengths, default=None),
        "blank_lines": sum(not line.strip() for line in lines),
        "list_lines": sum(bool(_LIST_LINE.match(line)) for line in lines),
        "uppercase_ratio": _ratio(sum(map(str.isupper, text)), cased),
        "ttr": _ratio(len(counts), word_count),
        "mattr": _mattr(words, window),
        "repeat_occurrence_ratio": _ratio(word_count - len(counts), word_count),
        "most_frequent_word_ratio": _ratio(max(counts.values(), default=0), word_count),
        "numeric_characters": numeric,
        "numeric_ratio": _ratio(numeric, characters),
        "numeric_expressions": len(_NUMBER.findall(text)),
        "date_patterns": len(_DATE.findall(text)),
        "time_patterns": len(_TIME.findall(text)),
        "special_ratio": _ratio(special, characters),
        "alphabetic_ratio": _ratio(letters, characters),
    }


def _punctuation(text: str) -> dict[str, int]:
    counts = Counter(char for char in text if unicodedata.category(char).startswith("P"))
    known = {sign: counts[sign] for sign in _PUNCTUATION}
    return {**known, "other": counts.total() - sum(known.values())}


def _distribution(values: list[int | float]) -> dict[str, int | float | None]:
    quartiles = quantiles(values, n=4, method="inclusive") if len(values) > 1 else values * 3
    return {
        "observed": len(values),
        "min": min(values, default=None),
        "q1": quartiles[0] if quartiles else None,
        "median": median(values) if values else None,
        "q3": quartiles[2] if quartiles else None,
        "max": max(values, default=None),
    }


def characterize_documents(
    documents: Sequence[Document], *, mattr_window: int = 50, include_entity_ids: bool = False
) -> dict[str, object]:
    """Return document metrics and distributions without serializing narrative or metadata."""
    if mattr_window < 2:
        raise ValueError("La ventana MATTR debe ser de al menos dos palabras.")
    if len({document.document_id for document in documents}) != len(documents):
        raise ValueError("El corpus debe tener identificadores documentales únicos.")

    text_hashes = [
        sha256(document.text.encode("utf-8")).hexdigest() if document.text is not None else None
        for document in documents
    ]
    frequencies = Counter(digest for digest in text_hashes if digest is not None)
    quality: Counter[str] = Counter(
        dict.fromkeys(
            (
                "unresolved_text",
                "empty",
                "whitespace_only",
                "exact_duplicate",
                "replacement_character",
                "unexpected_control",
                "bom",
            ),
            0,
        )
    )
    punctuation: Counter[str] = Counter()
    missing_text_metrics = dict.fromkeys(_text_metrics("", mattr_window))
    observed: dict[str, list[int | float]] = {name: [] for name in missing_text_metrics}
    observed["sections"] = []
    rows = []
    for document, text_hash in zip(documents, text_hashes, strict=True):
        text = document.text
        duplicate = text_hash is not None and frequencies[text_hash] > 1
        flags = {
            "unresolved_text": text is None,
            "empty": text == "",
            "whitespace_only": text is not None and text != "" and not text.strip(),
            "exact_duplicate": duplicate,
            "replacement_character": text is not None and "\ufffd" in text,
            "unexpected_control": text is not None
            and any(unicodedata.category(char) == "Cc" and char not in "\t\n\r" for char in text),
            "bom": text is not None and "\ufeff" in text,
        }
        quality.update({name: int(flag) for name, flag in flags.items()})
        metrics: dict[str, int | float | None] = {"sections": len(document.sections)}
        signs = None
        if text is not None:
            metrics.update(_text_metrics(text, mattr_window))
            signs = _punctuation(text)
            punctuation.update(signs)
        else:
            metrics.update(missing_text_metrics)
        for name, value in metrics.items():
            if value is not None:
                observed[name].append(value)
        row = {
            "document_id": document.document_id,
            "document_contract_sha256": content_hash(document),
            "text_sha256": text_hash,
            "has_text": text is not None,
            "exact_duplicate_group": text_hash if duplicate else None,
            "quality": flags,
            "metrics": metrics,
            "punctuation": signs,
        }
        if include_entity_ids:
            row["entity_id"] = document.entity_id
        rows.append(row)
    return {
        "method_version": METHOD_VERSION,
        "unicode_version": unicodedata.unidata_version,
        "parameters": {"mattr_window": mattr_window, "include_entity_ids": include_entity_ids},
        "corpus": {
            "documents": len(documents),
            "quality_counts": dict(quality),
            "exact_duplicate_groups": sum(count > 1 for count in frequencies.values()),
            "distributions": {
                name: {**_distribution(values), "missing": len(documents) - len(values)}
                for name, values in observed.items()
            },
            "punctuation": dict(punctuation),
        },
        "documents": rows,
    }


def sampling_scenarios(
    population: int,
    *,
    confidence: float = 0.95,
    margins: Sequence[float] = (0.03, 0.05, 0.07),
    discordance: Sequence[float] = (0.10, 0.25, 0.50),
) -> dict[str, object]:
    """Compare nominal precision under document-level simple random sampling."""
    if population < 1:
        raise ValueError("Los escenarios requieren un corpus de al menos un documento.")
    if not isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("La confianza debe estar entre cero y uno.")
    if not margins or any(not isfinite(value) or not 0 < value < 1 for value in margins):
        raise ValueError("Los márgenes deben estar entre cero y uno.")
    if any(not isfinite(value) or not 0 < value <= 1 for value in discordance):
        raise ValueError("La discordancia debe ser mayor que cero y como máximo uno.")
    # Use the lower tail to avoid rounding (1 + confidence) / 2 to exactly 1.
    z = -NormalDist().inv_cdf((1 - confidence) / 2)
    if z == 0:
        raise ValueError("El nivel de confianza es demasiado pequeño para el cálculo numérico.")
    scenarios = []
    models = [("proportion", 0.25, {"expected_proportion": 0.5})]
    models.extend(
        ("paired_binary_difference", q, {"assumed_discordance": q, "assumed_difference": 0.0})
        for q in discordance
    )
    for estimand, variance, assumptions in models:
        for margin in margins:
            scaled_variance = z**2 * variance
            corrected = (
                population * scaled_variance / ((population - 1) * margin**2 + scaled_variance)
            )
            scenarios.append(
                {
                    "estimand": estimand,
                    "assumptions": assumptions,
                    "margin": margin,
                    "documents_required": max(1, ceil(corrected)),
                }
            )
    return {
        "population_documents": population,
        "confidence": confidence,
        "design": "document_srs_without_replacement",
        "purpose": "illustrative_precision_only",
        "scenarios": scenarios,
    }
