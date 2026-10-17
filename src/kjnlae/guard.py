"""Model-only prompt-injection screening; authorization is a separate boundary."""

import os
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Protocol

from kjnlae.classifiers.artifacts import (
    ONNX_MANIFEST_SHA256,
    default_model_dir,
    verify_onnx_artifact,
)
from kjnlae.classifiers.local import LocalClassifier, LocalInference, LocalModelConfig
from kjnlae.context import TrustedSecurityContext
from kjnlae.detection.preprocessing import InspectionView, prepare_views
from kjnlae.policies.decision import InputPolicy
from kjnlae.schemas import Source
from kjnlae.schemas_v2 import (
    ContentEnvelope,
    InspectionRequestV2,
    InspectionResultV2,
    WindowEvidence,
)


class Classifier(Protocol):
    """Minimal inference contract shared by the SDK and test adapters."""

    def classify_views(self, views: Sequence[InspectionView], source: Source) -> LocalInference: ...


class Guard:
    """Inspect bounded text with a verified local model; never grants tool authority."""

    def __init__(
        self,
        classifier: Classifier | None = None,
        policy: InputPolicy | None = None,
        threshold: float | None = None,
        model_dir: str | None = None,
        model_hash: str | None = None,
    ) -> None:
        self.policy = policy or InputPolicy()
        self._configuration_error = ""
        self._model_missing = False
        self.classifier: Classifier | None = classifier
        if classifier is not None:
            self.threshold = threshold or 0.5
        else:
            directory = model_dir if model_dir is not None else os.getenv("KJNLAE_MODEL_DIR", "")
            manifest_hash = (
                model_hash if model_hash is not None else os.getenv("KJNLAE_MODEL_HASH", "")
            )
            if not directory and not manifest_hash:
                installed = default_model_dir()
                if installed.is_dir():
                    directory = str(installed)
                    manifest_hash = ONNX_MANIFEST_SHA256
            self.classifier = None
            self.threshold = 0.5
            if directory and manifest_hash:
                if not Path(directory).exists():
                    self._model_missing = True
                else:
                    try:
                        artifact = verify_onnx_artifact(Path(directory), manifest_hash)
                        self.threshold = artifact.threshold
                        self.classifier = LocalClassifier(
                            LocalModelConfig(artifact.path, manifest_hash)
                        )
                    except (OSError, ValueError, KeyError) as exc:
                        self._configuration_error = type(exc).__name__
            elif directory or manifest_hash:
                self._configuration_error = "MODEL_CONFIG_INCOMPLETE"

    def close(self) -> None:
        """Stop the local inference worker owned by this guard, if one exists."""
        if isinstance(self.classifier, LocalClassifier):
            self.classifier.close()

    def __enter__(self) -> "Guard":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def capabilities(self) -> dict[str, object]:
        """Report local artifact/worker state without downloading a model."""
        return {
            "detector": "fine_tuned_local_transformer_only",
            "model_status": (
                "MISSING"
                if self._model_missing
                else "CORRUPTED"
                if self._configuration_error
                else "MISSING"
                if self.classifier is None
                else "AVAILABLE"
                if isinstance(self.classifier, LocalClassifier) and self.classifier.is_ready()
                else "UNAVAILABLE"
            ),
            "model_config_error": self._configuration_error,
            "model_hash": (
                self.classifier.config.manifest_hash
                if isinstance(self.classifier, LocalClassifier)
                else None
            ),
            "threshold": self.threshold if self.classifier else None,
            "policy": self.policy.id,
        }

    def scan(self, text: str, **context: object) -> InspectionResultV2:
        """Validate a convenient SDK call, then use the same path as HTTP scans."""
        request = InspectionRequestV2.model_validate({"text": text, **context})
        return self.inspect(request)

    def inspect_chunks(
        self, chunks: Sequence[ContentEnvelope], trusted_context: TrustedSecurityContext
    ) -> list[InspectionResultV2]:
        """Inspect each retrieved chunk while retaining host-provided context."""
        return [
            self.inspect(InspectionRequestV2(text=chunk.text, source=chunk.source), trusted_context)
            for chunk in chunks
        ]

    def inspect(
        self,
        request: InspectionRequestV2,
        trusted_context: TrustedSecurityContext | None = None,
    ) -> InspectionResultV2:
        """Inspect all supported views and apply policy without granting authority.

        ``trusted_context`` must originate in host code. Failure or incomplete
        preprocessing/inference can never produce a cleared scan.
        """
        started = perf_counter()
        prepared = prepare_views(request.text)
        if self._model_missing:
            inference = LocalInference("MISSING", False, reason="MODEL_MISSING")
        elif self._configuration_error:
            inference = LocalInference("CORRUPTED", False, reason="ARTIFACT_INVALID")
        elif self.classifier is None:
            inference = LocalInference("MISSING", False, reason="MODEL_MISSING")
        else:
            inference = self.classifier.classify_views(prepared.views, request.source)
        outcome = self.policy.decide(
            inference, prepared.complete, request.source, trusted_context, self.threshold
        )
        windows = tuple(
            WindowEvidence(
                view=window.view,
                start=window.source_span[0],
                end=window.source_span[1],
                score=window.score,
                model_hash=inference.model_hash,
            )
            for window in inference.windows
            if window.score is not None and inference.model_hash is not None
        )
        evidence = tuple(window for window in windows if window.score >= self.threshold)
        return InspectionResultV2(
            detection_status=outcome.detection_status,
            policy_decision=outcome.decision,
            model_status=inference.status,
            evidence=evidence,
            windows=windows,
            threshold=self.threshold if inference.model_hash is not None else None,
            coverage={"views": len(prepared.views), "windows": len(inference.windows)},
            reason_codes=outcome.reason_codes + prepared.diagnostics,
            policy_id=self.policy.id,
            latency_ms=round((perf_counter() - started) * 1000, 3),
            inspection_complete=prepared.complete and inference.inspection_complete,
            model_hash=inference.model_hash,
            model_score=inference.score,
            risk_level=(
                "unknown"
                if outcome.detection_status == "INCOMPLETE"
                else "high"
                if outcome.decision == "BLOCK"
                else "elevated"
                if outcome.decision in {"WARN", "REQUIRE_REVIEW"}
                else "low"
            ),
            explanation=(
                "Model inspection incomplete; this content has not been cleared."
                if outcome.detection_status == "INCOMPLETE"
                else "The local fine-tuned model identified suspicious instruction content; "
                "this does not prove an attack succeeded."
                if outcome.detection_status == "MALICIOUS_INDICATORS"
                else "The local model found no injection indicators in the inspected content."
            ),
            recommended_action=(
                "Withhold automated use and require an authorized review."
                if outcome.decision == "REQUIRE_REVIEW"
                else "Do not use this content to trigger privileged actions."
                if outcome.decision == "BLOCK"
                else "Keep independent resource, tool and output controls in force."
            ),
        )
