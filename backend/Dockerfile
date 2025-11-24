FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
# We need to install playwright browsers and dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and system deps
RUN playwright install --with-deps chromium

COPY . .

# Create downloads directory
RUN mkdir -p downloads

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
