FROM python:3.11-slim

WORKDIR /app

# Copy dependency and package metadata
COPY pyproject.toml requirements.txt ./
COPY src/ ./src/

# Install package in editable/wheel mode
RUN pip install --no-cache-dir -e .

# Environment configuration
ENV PYTHONUNBUFFERED=1
ENV SQLITE_DB_PATH=/data/database.db

# Data volume directory for SQLite database files
RUN mkdir -p /data

ENTRYPOINT ["sqlite-mcp-server"]
CMD ["--transport", "stdio"]
