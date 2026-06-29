FROM python:3.12-slim

WORKDIR /app

# System deps for matplotlib (font rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py mcp_server.py engine.py engine_panel.py project_store.py config.txt ./
COPY static/ static/

RUN mkdir -p output

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
