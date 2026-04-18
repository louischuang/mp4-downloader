# YouTube to MP4 Downloader

A local web app and agent-friendly API for downloading YouTube videos, converting them to MP4, and generating transcripts.

- Docker deployment
- persistent video and transcript storage
- speech-to-text with `faster-whisper`
- quality selection
- live download and transcription progress
- Traditional Chinese, Simplified Chinese, English, and Japanese UI
- HTTP API, Swagger docs, CLI, and end-to-end test script

> Download only content you are allowed to save, and make sure you comply with YouTube terms and copyright rules.

## Preview

![App preview](assets/app-preview.svg)

## Features

- Paste a YouTube `watch`, `youtu.be`, `shorts`, or `embed` URL
- Choose output quality: `Best`, `1080p`, `720p`, or `360p`
- Start `Download` or `Download And Transcribe`
- Switch between YouTube download and local MP4 upload tabs
- Upload a local MP4 with a custom title
- Start transcription automatically after upload finishes
- See live status while downloading or transcribing
- Play local MP4 files, open the original YouTube page, and download generated files
- Generate `txt`, `srt`, `vtt`, and `json` transcript outputs
- Edit generated `srt` subtitles directly in the browser
- Generate a new MP4 with burned-in subtitles from the video list toolbar
- Switch UI language from the top-right button bar
- Persist downloaded files, transcripts, and model cache outside the container
- Support YouTube cookies for sign-in / anti-bot verification flows
- Expose agent-friendly API routes under `/api/v1/...`
- Provide Swagger UI at `/api/docs` and OpenAPI JSON at `/api/openapi.json`
- Provide a CLI via `python3 cli.py`
- Provide end-to-end API validation via `python3 scripts/e2e_api_test.py`

## Tech Stack

- Python `Flask`
- `yt-dlp`
- `faster-whisper`
- `ffmpeg`
- `nodejs` for YouTube JavaScript runtime support
- Docker / Docker Compose

## Quick Start With Docker

This project already includes:

- `Dockerfile`
- `docker-compose.yml`
- persistent storage mapping
- cookies mounting
- a dedicated STT container

Start the service:

```bash
docker-compose up --build -d
```

If your environment uses the newer Compose plugin:

```bash
docker compose up --build -d
```

Open the web UI:

```text
http://127.0.0.1:5001
```

Open Swagger UI:

```text
http://127.0.0.1:5001/api/docs
```

## Persistent Storage

Downloaded MP4 files, transcript outputs, and model cache are stored on the host through these bind mounts:

```yaml
volumes:
  - ./video-storage:/data/downloads
  - ./transcripts:/data/output
  - ./models:/models/huggingface
```

That means:

- files remain available after container restart
- files remain available after container rebuild
- videos, transcripts, and models stay outside the container filesystem

If you want to use another host folder, change it to something like:

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
```

Transcript output defaults to:

```text
./transcripts
```

Whisper model cache defaults to:

```text
./models
```

## YouTube Cookies Setup

If YouTube returns messages such as `Sign in to confirm you're not a bot`, export your YouTube cookies in Netscape format and place them here:

```text
./cookies/youtube.txt
```

Docker mounts that file to:

```text
/data/cookies/youtube.txt
```

Notes:

- the compose file mounts the cookies directory as read-only
- the app copies the cookie file into a writable temp location before calling `yt-dlp`
- the container also enables `YTDLP_REMOTE_COMPONENTS=ejs:github`

## Agent API

The project includes an agent-friendly HTTP API:

- `GET /api/health`
- `GET /api/capabilities`
- `POST /api/v1/downloads`
- `POST /api/v1/uploads`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/videos`
- `POST /api/v1/transcriptions`
- `GET /api/v1/transcriptions/{job_id}`
- `POST /api/v1/burned-videos`
- `GET /api/v1/subtitles/{filename}`
- `PUT /api/v1/subtitles/{filename}`

Related docs:

- Swagger UI: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`
- Detailed guide: [docs/AGENT_API.md](docs/AGENT_API.md)

## CLI

Examples:

```bash
python3 cli.py health
python3 cli.py capabilities --json
python3 cli.py videos --json
python3 cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --wait --json
python3 cli.py transcribe "example-video.mp4" --wait --json
```

## End-to-End Test Script

Run a full API validation flow:

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM"
```

Short summary output:

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM" --summary-only
```

## Local Development

If you want to run it without Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Then open:

```text
http://127.0.0.1:5000
```

For better MP4 merging on macOS:

```bash
brew install ffmpeg
```

## Project Structure

```text
.
├── app.py
├── cli.py
├── Dockerfile
├── docker-compose.yml
├── docs/
├── docker/
│   └── stt/
├── requirements.txt
├── scripts/
├── static/
├── templates/
├── assets/
├── cookies/
├── video-storage/
├── transcripts/
└── models/
```

## Usage

1. Open the app in your browser.
2. Choose `YouTube Download` or `Upload MP4`.
3. For YouTube mode, paste a YouTube video URL and choose your preferred quality.
4. For upload mode, choose a local MP4 file and enter a custom video title.
5. Click the main action button for the selected mode.
6. Watch the live progress bar and status text.
7. After download or upload, the STT job starts automatically when transcription is enabled or when using MP4 upload.
8. From the video list, you can play the video, open the original URL, download MP4, or download `txt` / `srt` / `vtt` / `json`.
9. If the transcript needs corrections, open `Edit Subtitles`, update the `srt`, and save it in the browser.
10. Use `Burn Subtitles MP4` to create a new MP4 with subtitles rendered into the video.

## Notes

- Without `ffmpeg`, the app falls back to formats that can be downloaded directly.
- With `ffmpeg`, separated audio/video streams can be merged into MP4.
- Burned subtitle MP4 generation also requires `ffmpeg`.
- The first `faster-whisper` run downloads model files into `./models`, then reuses cache later.
- Some YouTube videos may still require valid cookies, depending on account, region, age restriction, or anti-bot checks.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
