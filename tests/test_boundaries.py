"""Architecture guards and an isolated consumer with all model imports blocked."""

import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path


def test_core_imports_only_stdlib_pydantic_and_core():
    import extracteval.core

    core = Path(extracteval.core.__file__).parent
    allowed = sys.stdlib_module_names | {"pydantic", "extracteval"}
    for file in core.glob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert module.split(".")[0] in allowed, (file, module)
                if module.startswith("extracteval"):
                    assert module.startswith("extracteval.core"), (file, module)


def test_runtime_dependency_is_only_pydantic():
    requirements = importlib.metadata.requires("extracteval")
    runtime = [r for r in requirements if "extra ==" not in r]
    assert len(runtime) == 1 and runtime[0].startswith("pydantic")


def test_contracts_work_when_adapters_cannot_be_imported(tmp_path):
    code = """
import importlib.abc
import json
import sys
class BlockModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("extracteval.adapters"):
            raise AssertionError("Model initialization/import attempted")
sys.meta_path.insert(0, BlockModels())
from extracteval.core.documents import Document, EvidenceAssessment
from extracteval.core.reference import ExpertAnnotation
from extracteval.core.results import ExtractionResult, ResultTrace
from extracteval.core.base import ArtifactRef
from extracteval.core.experiments import ConfigRef
artifact = ArtifactRef(artifact_id="dictionary", version="1", sha256="a" * 64)
config = ConfigRef(config_id="experiment", version="1", sha256="b" * 64)
evidence = EvidenceAssessment(availability="absent", sufficiency="insufficient")
document = Document(document_id="doc", text="Synthetic administrative document")
trace = ResultTrace(document_id="doc", variable_id="decision", dictionary=artifact,
                    config=config, execution_id="run", output_schema=artifact)
result = ExtractionResult(result_id="result", trace=trace, operation="completed", evidence=evidence,
                          value={"kind": "categorical", "value": "indeterminado"})
annotation = ExpertAnnotation(annotation_id="annotation", document_id="doc", variable_id="decision",
    evaluator_id="expert", dictionary=artifact, partition="evaluation",
    blinded_to_system_output=True,
    status="evaluable", value={"kind": "categorical", "value": "indeterminado"}, evidence=evidence)
for obj in [document, result, annotation]:
    assert type(obj).model_validate_json(obj.model_dump_json()) == obj
print("offline contracts OK")
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert "offline contracts OK" in completed.stdout


def test_distribution_and_import_versions_match():
    import extracteval

    assert importlib.metadata.version("extracteval") == extracteval.__version__
