import asyncio

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client
from temporalio.worker import Worker

from app.activities import extract_pdf_content
from app.config import get_settings
from app.activities import extract_metadata, extract_pdf_content
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
            extract_pdf_content, # Activity for extraction all text from the PDF
            extract_metadata # Activity for extraction relevant metadata from PDF text
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
