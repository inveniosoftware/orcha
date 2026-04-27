FROM python:3.14-slim-bookworm

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv

# Copy the application into the container.
COPY . /app

# Install the application dependencies.
WORKDIR /app
RUN uv sync --locked --no-cache

# Run the application.
CMD ["/app/.venv/bin/fastapi", "run", "app/main.py", "--port", "8000"]
