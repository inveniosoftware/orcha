import asyncio

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client
from temporalio.worker import Worker

from app.activities import (
    extract_metadata_with_llm,
    extract_pdf_text,
    store_workflow_result,
)
from app.config import get_settings
from app.workflows.extract_metadata_workflow import ExtractMetadata


async def main():
    """Start the Temporal worker."""
    settings = get_settings()
    client = await Client.connect(
        settings.temporal_host,
        plugins=[PydanticAIPlugin()],
    )

    worker = Worker(
        client,
        task_queue="extract-pdf-metadata-task-queue",
        workflows=[
            ExtractMetadata,
        ],
        activities=[
            extract_pdf_text,  # Activity for extracting all text from the PDF
            extract_metadata_with_llm,  # Activity for extracting metadata via LLM
            store_workflow_result,  # Activity to persist status/results
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
