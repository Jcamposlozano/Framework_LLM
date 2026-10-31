"""Single-document phase 2 CLI. Offline mock mode is the default."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from extracteval.adapters.models.openai import OpenAIHTTPTransport, OpenAIResponsesModel
from extracteval.adapters.models.verification_mock import MockVerifierModel
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.configuration import GovernanceAuthorization, load_configuration
from extracteval.application.pipeline import run_verification
from extracteval.application.verification import IndependentVerifier, independent_request
from extracteval.core.hashing import content_hash
from extracteval.core.verification import VerificationInput, VerificationPayload


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "extract":
        from extracteval.extraction_cli import main as extract_main

        return extract_main(arguments[1:])
    parser = argparse.ArgumentParser(prog="extracteval")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("extract", help="Extract one document into immutable A")
    verify = commands.add_parser("verify", help="Independent documentary verification")
    verify.add_argument("--config", type=Path, required=True)
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument(
        "--stage", choices=("independent", "compare", "reconcile", "all"), default="all"
    )
    verify.add_argument("--mode", choices=("mock", "real"), default="mock")
    verify.add_argument("--dry-run", action="store_true")
    verify.add_argument("--authorize-real", action="store_true")
    verify.add_argument("--governance", type=Path)
    args = parser.parse_args(argv)
    mode = cast(Literal["mock", "real"], args.mode)
    stage = cast(Literal["independent", "compare", "reconcile", "all"], args.stage)
    try:
        config, dictionary, policy, verifier_config = load_configuration(
            args.config, os.environ, mode
        )
        inputs = VerificationInput.model_validate_json(args.input.read_bytes())
        independent_request(inputs.document, dictionary, verifier_config)
        if inputs.extraction_a:
            for result in inputs.extraction_a.results:
                result.validate_against(dictionary)
        mock_payload = None
        if mode == "mock":
            if config.mock_payload_path is None:
                raise ValueError("Mock mode requires an explicit synthetic payload fixture")
            mock_payload = VerificationPayload.model_validate_json(
                (args.config.resolve().parent / config.mock_payload_path).read_bytes()
            )
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "stage": stage,
                        "mode": mode,
                        "variables": len(dictionary.variables),
                        "provider_calls": 0,
                    }
                )
            )
            return 0
        network_needed = (
            mode == "real"
            and stage in ("all", "independent")
            and not (args.output / "verification.json").exists()
        )
        governance = None
        if network_needed:
            if not args.authorize_real or args.governance is None:
                raise ValueError("Real calls require --authorize-real and --governance")
            governance = GovernanceAuthorization.model_validate_json(args.governance.read_bytes())
            governance.validate_authorization(content_hash(inputs.document))
        verifier = None
        if stage in ("all", "independent") and not (args.output / "verification.json").exists():
            if mode == "mock":
                assert mock_payload is not None
                verifier = IndependentVerifier(MockVerifierModel([mock_payload]))
            else:
                transport = OpenAIHTTPTransport(os.environ.get("OPENAI_API_KEY", ""))
                verifier = IndependentVerifier(
                    OpenAIResponsesModel(verifier_config.model_id, transport)
                )
        store = JSONRunStore(args.output)
        if governance is not None:
            store.put("governance", governance)
        manifest = run_verification(
            inputs,
            dictionary,
            policy,
            verifier_config,
            store,
            verifier,
            stage=stage,
            mode=mode,
            mock_payload_hash=content_hash(mock_payload) if mock_payload else None,
        )
        print(
            json.dumps(
                {
                    "run_id": manifest.run_id,
                    "status": manifest.status,
                    "stage": stage,
                    "clinically_validated": False,
                }
            )
        )
        return 2 if manifest.status == "technical_failure" else 0
    except (OSError, ValueError, KeyError, ValidationError):
        # Validation messages may contain literal notes, paths or values. Never echo them here.
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": "invalid_configuration_input_or_artifact",
                    "hint": "Check contracts, integrity, stage prerequisites and authorization.",
                }
            )
        )
        return 2
