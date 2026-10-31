"""Single-document extractor CLI; network access requires explicit authorization."""

import argparse
import json
import os
from pathlib import Path
from typing import Literal, cast

from extracteval.adapters.models.openai import OpenAIHTTPTransport, OpenAIResponsesModel
from extracteval.adapters.models.verification_mock import MockExtractorModel
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.configuration import GovernanceAuthorization
from extracteval.application.extraction import extract_document, load_extractor
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.ports import ModelPort
from extracteval.core.verification import VerificationPayload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="extracteval extract")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--authorize-real", action="store_true")
    parser.add_argument("--governance", type=Path)
    args = parser.parse_args(argv)
    try:
        settings, dictionary, prompt = load_extractor(args.config, os.environ)
        document = Document.model_validate_json(args.input.read_bytes())
        if document.text is None:
            raise ValueError("Resolve document text locally first")
        mode = cast(Literal["mock", "real"], args.mode)
        payload = None
        if mode == "mock":
            if settings.mock_payload_path is None:
                raise ValueError("Mock requires an explicit fixture")
            payload = VerificationPayload.model_validate_json(
                (args.config.resolve().parent / settings.mock_payload_path).read_bytes()
            )
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "mode": mode,
                        "provider_calls": 0,
                        "variables": len(dictionary.variables),
                    }
                )
            )
            return 0
        model: ModelPort | None = None
        if not (args.output / "manifest.json").exists():
            if mode == "real":
                if not args.authorize_real or args.governance is None:
                    raise ValueError("Real extraction requires authorization")
                governance = GovernanceAuthorization.model_validate_json(
                    args.governance.read_bytes()
                )
                governance.validate_authorization(content_hash(document))
                model = OpenAIResponsesModel(
                    settings.model,
                    OpenAIHTTPTransport(os.environ.get("OPENAI_API_KEY", "")),
                    schema_name="clinical_extraction",
                    max_retries=0,
                )
            else:
                assert payload is not None
                model = MockExtractorModel([payload])
        store = JSONRunStore(args.output)
        if mode == "real" and model is not None:
            store.put("governance", governance)
        execution = extract_document(
            document,
            dictionary,
            settings,
            prompt,
            model,
            store,
            mode=mode,
            mock_payload_hash=content_hash(payload) if payload else None,
        )
        print(
            json.dumps(
                {
                    "base_extraction_id": execution.extraction_a.base_extraction_id,
                    "mode": mode,
                    "status": "technical_failure" if execution.audit.error else "completed",
                    "clinically_validated": False,
                }
            )
        )
        return 2 if execution.audit.error else 0
    except (OSError, ValueError, KeyError):
        print(json.dumps({"status": "error", "code": "invalid_extraction_configuration_or_input"}))
        return 2
