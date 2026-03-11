"""Simple LLM-based metadata extraction activity."""

import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from temporalio import activity


class DocumentMetadata(BaseModel):
    """Metadata extracted from a document."""
    title: str = Field(description="Main title of the document")
    abstract: str | None = Field(default=None, description="Document abstract")


class ExtractMetadataRequest(BaseModel):
    """Request to extract metadata from document text."""
    text: str = Field(description="Document text to analyze")
    model: str = Field(default="groq/qwen/qwen3-32b", description="Model to use")


INSTRUCTIONS = """\
Extract structured metadata from this document text.
Focus on finding the title and the abstract/summary.
Only include information that is clearly stated in the text.
"""


def _create_model(model_name: str):
    """Create a model using LiteLLM provider."""
    return OpenAIChatModel(
        model_name=model_name,
        provider=LiteLLMProvider(
            api_base="https://llmgw-litellm.web.cern.ch/v1",
            api_key=os.environ["LITELLM_API_KEY"],
        ),
    )


@activity.defn
async def extract_metadata(request: ExtractMetadataRequest) -> DocumentMetadata:
    """Extract metadata using LLM."""
    model = _create_model(request.model)
    agent = Agent(
        model=model,
        instructions=INSTRUCTIONS,
        output_type=DocumentMetadata,
    )

    result = await agent.run(request.text)
    return result.output
