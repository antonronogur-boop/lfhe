"""CR7-01 — provider-fixed sampling for models that reject `temperature` (PO instruction 2026-10-24)."""
from lfhe_orchestrator.model_settings import low_variance_problem, model_settings_problems
from lfhe_orchestrator.providers import AnthropicProvider, ModelConfig, PromptModule

MODULE = PromptModule("M07_INTELLIGENCE_ASSESSOR", "1.0.0", "a" * 64, "1", "SYSTEM PROMPT", "TASK", {})
FIXED = {"provider_fixed_sampling": True, "max_tokens": 16000, "timeout_seconds": 300}


def test_marker_rules():
    assert model_settings_problems("anthropic", "claude-sonnet-5-5", FIXED) == []
    assert model_settings_problems("anthropic", "claude-x", {"provider_fixed_sampling": False}) == ["$.provider_fixed_sampling (MUST_BE_TRUE)"]
    assert model_settings_problems("anthropic", "claude-x", {"provider_fixed_sampling": 1}) == ["$.provider_fixed_sampling (MUST_BE_TRUE)"]
    assert model_settings_problems("anthropic", "claude-x", {"provider_fixed_sampling": True, "temperature": 0}) == [
        "$.provider_fixed_sampling (CONFLICTS_WITH_SAMPLING_PARAMETER)"]
    assert model_settings_problems("fake", "fake-model", {"provider_fixed_sampling": True}) == [
        "$.provider_fixed_sampling (SETTING_NOT_ALLOWED_FOR_PROVIDER)"]


def test_low_variance_accepts_only_the_explicit_marker():
    assert low_variance_problem("M10_QA_AUDITOR", FIXED) is None
    assert low_variance_problem("M10_QA_AUDITOR", {"max_tokens": 100})                    # neither → still refused
    assert low_variance_problem("M10_QA_AUDITOR", {"temperature": 0.7})                   # unchanged rule
    assert low_variance_problem("M02_CLAIM_EXTRACTOR", {"temperature": 0}) is None


def test_adapter_sends_no_sampling_parameter_with_the_marker_and_unchanged_body_otherwise():
    fixed = AnthropicProvider.render_request(MODULE, {"x": 1}, ModelConfig("anthropic", "claude-sonnet-5-5", FIXED))
    assert "temperature" not in fixed and "top_p" not in fixed and fixed["max_tokens"] == 16000
    assert set(fixed) == {"model", "max_tokens", "system", "messages"}
    classic = AnthropicProvider.render_request(MODULE, {"x": 1}, ModelConfig("anthropic", "claude-x", {"temperature": 0, "max_tokens": 10}))
    assert classic["temperature"] == 0 and "top_p" not in classic
