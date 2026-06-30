# MCP Panel

AI-powered CAD design copilot for acoustic products (splitter silencers and stratified acoustic panels). Built with FastAPI, Gemini, and MCP tools.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A [Gemini API key](https://aistudio.google.com/app/apikey)

## Setup

**1. Clone the repo**

```bash
git clone <repo-url>
cd Task
```

**2. Create the `.env` file**

```bash
cp .env.example .env   # or create it manually
```

Add your key:

```
GEMINI_API_KEY=your_key_here
```

**3. Create the data directory**

```bash
mkdir data
```

This is where the SQLite database (`data/projects.db`) will be stored. It is mounted into the container so data persists across restarts.

**4. Build and run**

```bash
docker compose up --build
```

The app will be available at [http://localhost:8000](http://localhost:8000).

## Running without Docker

```bash
python -m venv env
source env/bin/activate      # Windows: env\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

## Project structure

```
app.py            FastAPI backend + Gemini agent loop
mcp_server.py     MCP tool definitions
engine.py         Silencer drawing engine
engine_panel.py   Panel drawing engine
project_store.py  SQLite-backed project persistence
email_intake.py   Email intake router (parse, review, confirm/reject)
email_extract.py  Gemini-powered parameter extractor
email_propose.py  Proposal builder from extracted parameters
email_pending.py  In-memory store for pending change proposals
data/             Mounted volume — contains projects.db
output/           Generated drawings (Docker named volume)
static/           Frontend assets
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/chat` | Send a message to the AI copilot |
| GET | `/output/<file>` | Retrieve a generated drawing |

### Email intake

| Method | Path | Description |
|--------|------|-------------|
| POST | `/email/incoming` | Receive an email (`sender`, `subject`, `body`); extracts parameters with Gemini and parks actionable changes for review |
| GET | `/email/pending` | Browser UI listing all pending change proposals with confirm/reject buttons |
| POST | `/email/confirm/{token}` | Approve a pending proposal and commit the parameter change to the project |
| POST | `/email/reject/{token}` | Discard a pending proposal without making any changes |
