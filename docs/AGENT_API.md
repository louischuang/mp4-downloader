# Agent API and CLI Guide

This project now exposes an agent-friendly HTTP API and a CLI wrapper for other platforms, scripts, and AI agents.

## Swagger / OpenAPI

- Swagger UI: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`

## Design Principles

- Versioned API paths under `/api/v1/...`
- Async download and transcription jobs for long-running work
- JSON-first responses that are easy for AI agents to parse
- Capability discovery so external agents can check supported features before calling workflows

## Main Endpoints

### `GET /api/health`

Returns runtime readiness:

- `yt_dlp_ready`
- `ffmpeg_ready`
- `stt_reachable`

### `GET /api/capabilities`

Returns:

- supported download qualities
- supported transcription models
- available features

### `POST /api/v1/downloads`

Request:

```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "quality": "720p"
}
```

Response:

```json
{
  "job_id": "6e23f2f4f9ec48fcae0a6e8d2296d4de",
  "status_url": "/api/v1/jobs/6e23f2f4f9ec48fcae0a6e8d2296d4de"
}
```

### `GET /api/v1/jobs/{job_id}`

Returns download job state such as:

- `queued`
- `running`
- `completed`
- `error`

When completed, `filename` and `download_url` are included.

### `GET /api/v1/videos`

Lists all downloaded MP4 files and transcript artifacts.

### `POST /api/v1/transcriptions`

Request:

```json
{
  "filename": "example-video.mp4",
  "model": "small"
}
```

### `GET /api/v1/transcriptions/{job_id}`

Returns STT job status and generated transcript download URLs when available.

## CLI

Run from the project root:

```bash
python cli.py health
python cli.py capabilities
python cli.py videos --json
python cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --quality 720p --wait
python cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --wait --transcribe --model small --json
python cli.py transcribe "example-video.mp4" --wait --json
python cli.py job <download-job-id> --json
python cli.py transcription-status <transcription-job-id> --json
```

Optional global flags:

- `--base-url http://127.0.0.1:5000`
- `--json`

## E2E Test Script

Run a full end-to-end API validation:

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM"
```

Short summary output:

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM" --summary-only
```

What it validates:

- `GET /api/health`
- `GET /api/capabilities`
- `POST /api/v1/downloads`
- `GET /api/v1/jobs/{job_id}` until completion
- `GET /api/v1/videos`
- `POST /api/v1/transcriptions`
- `GET /api/v1/transcriptions/{job_id}` until completion
- MP4 download
- `txt`, `srt`, `vtt`, `json` transcript downloads

## Suggested Agent Workflow

1. Call `GET /api/health`
2. Call `GET /api/capabilities`
3. Submit `POST /api/v1/downloads`
4. Poll `GET /api/v1/jobs/{job_id}`
5. After completion, optionally submit `POST /api/v1/transcriptions`
6. Poll `GET /api/v1/transcriptions/{job_id}`

This structure keeps the HTTP API simple and stable while letting the CLI provide a higher-level automation experience for agents.
