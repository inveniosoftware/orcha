# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Shared LLM agent builder."""

from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.providers.ollama import OllamaProvider

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)

# Extra instruction pieces for prompted output (models without native tool calls):
# cap reasoning, then force a single JSON object.
_REASONING_LOW = "Reasoning: low"
_JSON_ONLY = (
    "Respond immediately; do not deliberate. "
    "Reply with exactly one JSON object matching the schema and nothing else."
)
# Retries for output validation errors
_OUTPUT_RETRIES = 2


def _parse_llm(llm: str) -> tuple[str, str]:
    provider, sep, model_name = llm.partition("/")
    if not sep:
        raise ValueError("Invalid LLM; expected '<provider>/<model>'")
    provider = provider.strip().lower()
    model_name = model_name.strip()
    if provider not in {"litellm", "ollama"}:
        raise ValueError("Invalid LLM; provider must be 'litellm' or 'ollama'")
    if not model_name:
        raise ValueError("Invalid LLM; model name is missing")
    return provider, model_name


def build_agent(llm: str, output_type: type[T], instructions: str) -> Agent[None, T]:
    """Build the extraction agent for `llm` from the configured settings."""
    settings = get_settings()
    cfg = settings.llm_settings
    provider_name, model_name = _parse_llm(llm)

    if provider_name == "ollama":
        provider = OllamaProvider(
            base_url=settings.ollama_base_url, api_key=settings.ollama_api_key
        )
    else:
        provider = LiteLLMProvider(
            api_base=settings.litellm_api_base, api_key=settings.litellm_api_key
        )

    model = OpenAIChatModel(
        model_name=model_name,
        provider=provider,
        settings=OpenAIChatModelSettings(**cfg.model),
    )
    if cfg.output == "prompted":
        return Agent[None, T](
            model,
            instructions=[_REASONING_LOW, instructions, _JSON_ONLY],
            output_type=PromptedOutput(output_type),
            retries=_OUTPUT_RETRIES,
        )
    return Agent[None, T](
        model,
        instructions=instructions,
        output_type=output_type,
        retries=_OUTPUT_RETRIES,
    )
