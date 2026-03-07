# Stage 1: Install dependencies
# Using slim variant for smaller image size while keeping essential system libs
FROM python:3.11-slim AS deps

WORKDIR /app

# Install dependencies first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image with application code
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source code
COPY src/ src/
COPY scripts/ scripts/

# Create directories for runtime data
RUN mkdir -p pdfs

# Expose the port uvicorn will listen on
EXPOSE 8080

# Run the FastAPI app with uvicorn, binding to all interfaces
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
