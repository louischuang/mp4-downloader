# Agent API and CLI Guide

This project now exposes an agent-friendly HTTP API and a CLI wrapper for other platforms, scripts, and AI agents. Transcription jobs can target a dedicated local STT container or a remote Whisper service that accepts uploaded MP4 files and returns transcript artifacts.

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

### `POST /api/v1/uploads`

Uploads a local MP4 file and starts transcription automatically.

Multipart form fields:

- `title`
- `file`
- `model`

Response includes:

- uploaded `filename`
- `title`
- `transcription_job_id`
- `video` metadata snapshot

The web app stores the uploaded MP4 locally, uploads the same MP4 to the STT service, and later pulls transcript artifacts back into local `transcripts`.

### `POST /api/v1/burned-videos`

Creates a new MP4 with subtitles burned into the video.

Request:

```json
{
  "filename": "example-video.mp4",
  "style": {
    "size": "plus_20",
    "font_family": "sans",
    "text_color": "#ffffff",
    "outline_color": "#000000",
    "outline_width": 1.2,
    "position": "bottom",
    "line_spacing": 2,
    "margin_v": 34,
    "margin_l": 42,
    "margin_r": 42,
    "shadow": false,
    "background": true,
    "background_color": "#000000",
    "background_opacity": 48,
    "background_size": 24,
    "background_radius": 18,
    "max_chars_per_line": 18
  }
}
```

Supported `style` fields:

- `size`: `minus_20`, `minus_10`, `zero`, `plus_10`, `plus_20`, `plus_30`
- `font_family`: `sans`, `serif`, `mono`
- `text_color`, `outline_color`, `background_color`: hex colors like `#ffffff`
- `outline_width`
- `position`: `bottom`, `middle`, `top`
- `line_spacing`
- `margin_v`, `margin_l`, `margin_r`
- `shadow`
- `background`
- `background_opacity`
- `background_size`
- `background_radius`
- `max_chars_per_line`

Response includes:

- `job_id`
- `status_url`
- source `filename`

### `GET /api/v1/subtitles/{filename}`

Returns the editable `srt` content for a given MP4 file.

Response includes:

- video `filename`
- subtitle `filename`
- raw `content`

### `PUT /api/v1/subtitles/{filename}`

Updates the `srt` content for a given MP4 file.

Request:

```json
{
  "content": "1\n00:00:00,000 --> 00:00:02,000\nHello world\n"
}
```

Response includes:

- video `filename`
- subtitle `filename`
- `updated_at`

### `POST /api/v1/transcriptions`

Starts a transcription job for an MP4 already stored by the web app. The web app uploads that MP4 to the STT service instead of relying on shared storage.

Request:

```json
{
  "filename": "example-video.mp4",
  "model": "small"
}
```

### `GET /api/v1/transcriptions/{job_id}`

Returns STT job status and generated transcript download URLs when available. When the remote STT job is `completed`, the web app pulls transcript artifacts back and saves them locally before serving transcript download URLs.

## CLI

Run from the project root:

```bash
python cli.py health
python cli.py capabilities
python cli.py videos --json
python cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --quality 720p --wait
python cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --wait --transcribe --model small --json
python cli.py transcribe "example-video.mp4" --wait --json
python cli.py burn "example-video.mp4" --wait --size plus_20 --font-family sans --text-color "#ffffff" --outline-color "#000000" --background --background-color "#000000" --background-opacity 48 --background-size 24 --background-radius 18
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

## Remote STT Notes

- Configure the web app with `STT_API_URL` pointing to your dedicated Whisper service
- The remote Whisper service should provide:
  - `POST /jobs`
  - `GET /jobs/{job_id}`
  - `GET /jobs/{job_id}/artifacts`
- The first `large-v3` run may stay in `stt.loading_model` while the remote service downloads model weights

## Suggested Agent Workflow

1. Call `GET /api/health`
2. Call `GET /api/capabilities`
3. Submit `POST /api/v1/downloads`
4. Poll `GET /api/v1/jobs/{job_id}`
5. After completion, optionally submit `POST /api/v1/transcriptions`
6. Or upload an MP4 with `POST /api/v1/uploads`
7. Poll `GET /api/v1/transcriptions/{job_id}`
8. If transcript text needs correction, read `GET /api/v1/subtitles/{filename}` and update it with `PUT /api/v1/subtitles/{filename}`
9. Submit `POST /api/v1/burned-videos` to create a subtitle-burned MP4

This structure keeps the HTTP API simple and stable while letting the CLI provide a higher-level automation experience for agents.
