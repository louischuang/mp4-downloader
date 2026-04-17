# YouTube to MP4 Downloader

A local web app for downloading YouTube videos to MP4 with:

- Docker deployment
- persistent video storage
- quality selection
- live download progress
- Traditional Chinese, Simplified Chinese, English, and Japanese UI

> Download only content you are allowed to save, and make sure you comply with YouTube terms and copyright rules.

## Preview

![App preview](assets/app-preview.svg)

## Features

- Paste a YouTube `watch`, `youtu.be`, `shorts`, or `embed` URL
- Choose output quality: `Best`, `1080p`, `720p`, or `360p`
- See progress and status updates while downloading
- Download merged MP4 output when `ffmpeg` is available
- Switch UI language from the top-right button bar
- Persist downloaded files outside the container
- Support YouTube cookies for sign-in / anti-bot verification flows

## Tech Stack

- Python `Flask`
- `yt-dlp`
- `ffmpeg`
- `nodejs` for YouTube JavaScript runtime support
- Docker / Docker Compose

## Quick Start With Docker

This project is intended to run with Docker and already includes:

- `Dockerfile`
- `docker-compose.yml`
- persistent storage mapping
- cookies mounting

Start the service:

```bash
docker-compose up --build -d
```

If your environment uses the newer Compose plugin:

```bash
docker compose up --build -d
```

Open the app in your browser:

```text
http://127.0.0.1:5001
```

## Persistent Storage

Downloaded MP4 files are stored on the host machine through this bind mount:

```yaml
volumes:
  - ./video-storage:/data/downloads
```

That means:

- files remain available after container restart
- files remain available after container rebuild
- downloaded videos stay outside the container filesystem

If you want to use another host folder, change it to something like:

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
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
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
├── templates/
├── assets/
├── cookies/
└── video-storage/
```

## Usage

1. Open the app in your browser.
2. Paste a YouTube video URL.
3. Choose your preferred quality.
4. Click the download button.
5. Watch the live progress bar and status text.
6. Download the resulting MP4 from the completed job panel.

## Notes

- Without `ffmpeg`, the app falls back to formats that can be downloaded directly.
- With `ffmpeg`, separated audio/video streams can be merged into MP4.
- Some YouTube videos may still require valid cookies, depending on account, region, age restriction, or anti-bot checks.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
