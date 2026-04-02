# 🜂 IDIM IKANG v1.1-tuned

**Codex ID:** mo-fin-idim-ikang-001
**Phase:** v1.1 — Lawful Observer (Tuned)

## Architecture
- **Quant Core:** Python / FastAPI
- **Database:** Neon PostgreSQL / Local PostgreSQL (Append-only)
- **Hosting Target:** Hetzner VPS (Frankfurt)

## Deployment Instructions (Hetzner)

1. Provision an Ubuntu 22.04/24.04 VPS on Hetzner (Frankfurt region).
2. Install Docker and Docker Compose.
3. Setup PostgreSQL (if not using Neon):
   ```bash
   docker run --name idim-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:15
   ```
4. Apply `schema.sql` to the database.
5. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
6. Configure environment variables in a `.env` file:
   ```env
   # Use DATABASE_URL for Neon Postgres, or individual vars for local
   DATABASE_URL=postgres://user:pass@ep-cool-db.region.aws.neon.tech/dbname?sslmode=require
   DB_HOST=localhost
   DB_PORT=5432
   DB_USER=postgres
   DB_PASS=postgres
   DB_NAME=postgres
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```
7. Run the FastAPI server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
8. Trigger the scanner:
   ```bash
   curl -X POST http://localhost:8000/start
   ```
9. Kill switch (Manual halt):
   ```bash
   curl -X POST http://localhost:8000/kill
   ```
