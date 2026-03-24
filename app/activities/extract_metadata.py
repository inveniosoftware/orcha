"""LLM-based metadata suggestions activity."""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.providers.ollama import OllamaProvider
from temporalio import activity

from app.config import get_settings
from app.workflows.suggestions import MetadataResult


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


class ExtractMetadataRequest(BaseModel):
    """Request to generate metadata suggestions from document text."""

    text: str = Field(description="Document text to analyze")


INSTRUCTIONS = """\
You generate metadata suggestions from document text.

Return a list of typed suggestions for the following fields:
- title (string)
- description (string; the abstract/summary)
- creators (list of objects with: name, affiliation (optional), orcid (optional))
- doi (string; the Digital Object Identifier")
- publication_date (string; ISO 8601, examples:
    - "2014-07-17" (full date known)
    - "2014" (only year known)
    - Input: "17 July 2023" -> Output: "2023-07-17"
    - Input: "July 2023" -> Output: "2023"
    - Input: "2023-07" -> Output: "2023")

Rules:
- Only include information that is clearly stated in the text.
- If a field is not present or cannot be determined, omit that suggestion entirely.
- For creators.name, use the "Family, Given" format.
"""


def _create_model() -> OpenAIChatModel:
    """Create an OpenAI-compatible chat model from settings."""
    settings = get_settings()
    provider_name, model_name = _parse_llm(settings.llm)

    if provider_name == "ollama":
        provider = OllamaProvider(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
        )
    else:
        provider = LiteLLMProvider(
            api_base=settings.litellm_api_base,
            api_key=settings.litellm_api_key,
        )

    return OpenAIChatModel(model_name=model_name, provider=provider)


@activity.defn
async def extract_metadata_with_llm(
    request: ExtractMetadataRequest,
) -> MetadataResult:
    """Generate typed metadata suggestions using an LLM."""
    model = _create_model()
    agent = Agent(
        model=model,
        instructions=INSTRUCTIONS,
        output_type=MetadataResult,
    )

    result = await agent.run(request.text)
    return result.output
