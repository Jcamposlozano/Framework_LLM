import hashlib
import json
import sys
from pathlib import Path

import pytest

from extracteval.application.document_characterization import (
    characterize_documents,
    sampling_scenarios,
)
from extracteval.core.documents import Document, DocumentSection
from extracteval.core.hashing import content_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from laboratorio import main  # noqa: E402


def test_document_metrics_and_exact_duplicates():
    narrative = "Árbol árbol sol.\n\n- Sol 2026-11-24 09:30"
    first = Document(
        document_id="synthetic-1",
        entity_id="synthetic-group",
        text=narrative,
        sections=(DocumentSection(name="example", start=0, end=5),),
    )
    second = Document(document_id="synthetic-2", text=narrative)
    report = characterize_documents([first, second], mattr_window=3)
    row, copy = report["documents"]

    assert row["document_contract_sha256"] == content_hash(first)
    assert row["document_contract_sha256"] != copy["document_contract_sha256"]
    assert row["exact_duplicate_group"] == copy["exact_duplicate_group"] == row["text_sha256"]
    assert row["text_sha256"] == hashlib.sha256(narrative.encode()).hexdigest()
    assert "entity_id" not in row
    assert "Árbol" not in json.dumps(report, ensure_ascii=False)
    assert row["punctuation"]["."] == 1
    metrics = row["metrics"]
    assert metrics["sections"] == 1
    assert metrics["words"] == 4
    assert metrics["unique_words"] == 2
    assert metrics["median_word_length"] == 4
    assert metrics["lines"] == 3
    assert metrics["paragraphs"] == 2
    assert metrics["estimated_sentences"] == 2
    assert metrics["mean_sentence_words"] == 2
    assert metrics["blank_lines"] == 1
    assert metrics["list_lines"] == 1
    assert metrics["ttr"] == metrics["repeat_occurrence_ratio"] == 0.5
    assert metrics["mattr"] == pytest.approx(2 / 3)
    assert metrics["most_frequent_word_ratio"] == 0.5
    assert metrics["date_patterns"] == metrics["time_patterns"] == 1
    assert report["corpus"]["exact_duplicate_groups"] == 1
    assert report["corpus"]["distributions"]["words"]["median"] == 4
    authorized = characterize_documents([first], include_entity_ids=True)
    assert authorized["documents"][0]["entity_id"] == "synthetic-group"


def test_missing_text_empty_whitespace_and_encoding_indicators():
    report = characterize_documents(
        [
            Document(document_id="reference-only", text_ref="external-reference"),
            Document(document_id="empty", text=""),
            Document(document_id="blank", text=" \t\n"),
            Document(document_id="encoding", text="\ufeffx\ufffd\x00"),
        ]
    )
    unresolved, empty, blank, encoding = report["documents"]
    assert unresolved["has_text"] is False
    assert unresolved["text_sha256"] is None
    assert unresolved["metrics"]["words"] is None
    assert "external-reference" not in json.dumps(report)
    assert empty["has_text"] is True
    assert empty["quality"]["empty"] and not empty["quality"]["whitespace_only"]
    assert empty["metrics"]["words"] == 0
    assert empty["metrics"]["ttr"] is None
    assert blank["quality"]["whitespace_only"]
    assert blank["metrics"]["non_whitespace_characters"] == 0
    assert encoding["metrics"]["mattr"] is None
    for key in ("bom", "unexpected_control", "replacement_character"):
        assert encoding["quality"][key] is True
    assert report["corpus"]["distributions"]["words"]["missing"] == 1


def test_unicode_normalization_applies_only_to_lexical_metrics():
    docs = [
        Document(document_id="first", text="É é"),
        Document(document_id="second", text="E\u0301 e\u0301"),
    ]
    first, second = characterize_documents(docs, mattr_window=2)["documents"]
    assert first["metrics"]["mattr"] == second["metrics"]["mattr"] == 0.5
    assert first["text_sha256"] != second["text_sha256"]
    assert first["exact_duplicate_group"] is None
    with pytest.raises(ValueError, match="únicos"):
        characterize_documents([docs[0], docs[0]])
    with pytest.raises(ValueError, match="al menos dos"):
        characterize_documents(docs, mattr_window=1)


def test_finite_population_scenarios():
    report = sampling_scenarios(5924, margins=[0.05])
    scenarios = report["scenarios"]
    assert report["design"] == "document_srs_without_replacement"
    assert scenarios[0]["documents_required"] == 361
    assert scenarios[1]["documents_required"] < 361 < scenarios[3]["documents_required"]
    assert sampling_scenarios(1)["scenarios"][0]["documents_required"] == 1
    with pytest.raises(ValueError, match="márgenes"):
        sampling_scenarios(10, margins=[float("nan")])


def test_lab_cli_preserves_corpus_and_design_and_refuses_overwrite(tmp_path, monkeypatch):
    (tmp_path / "datos").mkdir()
    (tmp_path / "02_diseno").mkdir()
    corpus = tmp_path / "datos/documentos.json"
    source = b'[{"document_id":"synthetic-1","text":"synthetic narrative"}]'
    corpus.write_bytes(source)
    design = tmp_path / "02_diseno/resultados.json"
    prior = b'{"muestra": [], "particiones": [], "metadata": "existing"}'
    design.write_bytes(prior)

    command = ["laboratorio.py", "caracterizar-documentos", "--laboratorio", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", command + ["--ventana-mattr", "2", "--margen", "0.05"])
    main()
    output = tmp_path / "02_diseno/caracterizacion-documental.json"
    data = output.read_bytes()
    report = json.loads(data)
    assert report["source"]["sha256"] == hashlib.sha256(source).hexdigest()
    assert report["parameters"]["mattr_window"] == 2
    assert report["sampling_scenarios"]["population_documents"] == 1
    assert b"synthetic narrative" not in data
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit, match="2"):
        main()
    assert output.read_bytes() == data
    assert corpus.read_bytes() == source
    assert design.read_bytes() == prior


def test_cli_errors_do_not_echo_document_content(tmp_path, monkeypatch, capsys):
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos/documentos.json").write_text(
        '[{"document_id":"invalid identifier","text":"synthetic secret marker"}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv", ["laboratorio.py", "caracterizar-documentos", "--laboratorio", str(tmp_path)]
    )
    with pytest.raises(SystemExit, match="2"):
        main()
    captured = capsys.readouterr()
    assert "contrato documental" in captured.err
    assert "synthetic secret marker" not in captured.err
    assert not (tmp_path / "02_diseno/caracterizacion-documental.json").exists()
