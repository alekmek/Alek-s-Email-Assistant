# Alek's Email Assistant

Voice-first email assistant with real-time audio conversation, inbox search, message analysis, and reply workflows.

## What This Tool Does

- Lets users talk naturally to manage inbox tasks.
- Supports accurate counting and filtering across large email sets.
- Classifies email breakdowns (spam, important, personal, automated, work, other).
- Reads and summarizes message content.
- Processes common attachment types (PDF, image, Word, Excel, text).
- Supports safety controls (permissions, exclusions, limits).
- Supports user profile credential configuration from the UI.

## Architecture

```text
Browser (React + Vite)
  - UI state, transcript rendering, conversation history
  - WebSocket audio client
  - Settings/Profile UI (safety + credentials)
        |
        | WebSocket (/ws/audio) + REST (/api/*)
        v
Backend (FastAPI + Pipecat pipeline)
  - STT (speech-to-text)
  - LLM orchestration + tool calling
  - TTS (text-to-speech)
  - Tool execution (email + attachments)
  - Conversation/state APIs
  - Profile and safety settings APIs
        |
        +--> Nylas API (email access)
        +--> SQLite (conversations + settings + profile)
```

## Core Runtime Flow

1. Frontend connects to `/ws/audio`.
2. User speech is streamed as PCM audio.
3. Backend transcribes speech and sends text to the LLM context.
4. LLM calls tools when needed (`search_emails`, `count_emails`, `get_email_breakdown`, etc.).
5. Tool results are sent back through the same conversation turn.
6. Assistant response is synthesized to audio and streamed to client.
7. Transcript, tool activity, ETA, and email card payloads update in real time.

## Functionality

### Email tools

- `search_emails`: filtered search with sampled result payload + optional exact total count.
- `count_emails`: exact count with pagination across full matching dataset.
- `get_email_breakdown`: exact categorized breakdown across full matching dataset.
- `get_email_details`: full content for a selected message.
- `list_unread`: unread list for quick triage.
- `send_reply`: create draft or send reply.
- `mark_as_read`: update message read state.
- `read_attachment`: analyze supported attachments.

### Safety and controls

- Permission toggles for sending, reading, marking, deleting, archiving.
- Exclusion lists for senders/folders/subject keywords.
- Max emails-per-search control.
- Sensitive-content handling toggle.

### Profile and credentials

- Display name management.
- Provider credential status (configured + source).
- Credential updates via UI (`Settings` modal).
- Runtime resolves credentials profile-first, then environment fallback.

## API Surface (high level)

- Conversation:
  - `GET /api/conversations`
  - `POST /api/conversations`
  - `GET /api/conversations/{id}`
  - `GET /api/conversations/{id}/messages`
  - `POST /api/conversations/{id}/messages`
  - `DELETE /api/conversations/{id}`
- Settings:
  - `GET /api/settings`
  - `PUT /api/settings`
- Profile:
  - `GET /api/profile`
  - `PUT /api/profile`
  - `PUT /api/profile/credentials`
- Health:
  - `GET /`
  - `GET /health`
- Audio:
  - `WS /ws/audio`

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- API credentials for:
  - Anthropic
  - Nylas
  - Deepgram
  - Cartesia

### Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate
pip install -e .
```

Copy env template and configure:

```bash
cp .env.example backend/.env
```

Required backend env values:

```env
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
NYLAS_API_KEY=
NYLAS_CLIENT_ID=
NYLAS_CLIENT_SECRET=
NYLAS_GRANT_ID=
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=
HOST=0.0.0.0
PORT=8000
FRONTEND_URL=http://localhost:5173
```

Run backend:

```bash
cd backend
python -m app.main
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Deployment

- Terraform implementation is under `terraform/`.
- Step-by-step rollout plan is in `terraform_plan.md`.

## Project Layout

```text
backend/
  app/
    main.py
    config.py
    models/
    services/
    pipecat_bot/
frontend/
  src/
    components/
    hooks/
    services/
    store/
terraform/
  *.tf
```
