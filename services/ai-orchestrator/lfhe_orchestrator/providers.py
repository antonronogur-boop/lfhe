"""Provider abstraction (ADR-0004).

A provider receives the exact, registered prompt module (from the database
copy of the activated artifact), the input envelope, and the model
configuration; it returns raw text only. Parsing and schema validation are
done by the runner, never by the provider, so every provider is held to the
same output contract.

Phase 1 ships only ``FakeProvider`` (tests). Real provider adapters need
secret-manager integration and are Phase 2 work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class PromptModule:
    module_code: str
    semver: str
    content_hash: str
    module_version: str
    system: str
    task: str
    output_schema: dict


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    settings: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    raw_text: str
    usage: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Provider(Protocol):
    name: str

    def run_structured_task(self, module: PromptModule, envelope: dict, model_config: ModelConfig) -> ProviderResponse:
        ...


class FakeProvider:
    """Deterministic provider for tests: ``responder(module, envelope)`` returns
    the raw text (or raises ProviderError)."""
    name = "fake"

    def __init__(self, responder: Callable[[PromptModule, dict], str]):
        self.responder = responder
        self.calls: list[tuple[PromptModule, dict, ModelConfig]] = []

    def run_structured_task(self, module: PromptModule, envelope: dict, model_config: ModelConfig) -> ProviderResponse:
        self.calls.append((module, envelope, model_config))
        text = self.responder(module, envelope)
        return ProviderResponse(text, {"input_chars": len(module.system) + len(module.task) + len(str(envelope)),
                                       "output_chars": len(text)})


__all__ = ["FakeProvider", "ModelConfig", "PromptModule", "Provider", "ProviderError", "ProviderResponse", "Any"]
