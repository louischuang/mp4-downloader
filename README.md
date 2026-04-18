# YouTube to MP4 Downloader

Choose your language:

- [English](README.en.md)
- [繁體中文](README.zh-Hant.md)
- [简体中文](README.zh-Hans.md)
- [日本語](README.ja.md)

Quick links:

- [License](LICENSE)
- [App Preview](assets/app-preview.svg)
- [Agent API & CLI Guide](docs/AGENT_API.md)
- [Tool Usage Guide](docs/TOOL_USAGE.md)
- [CLI Guide](docs/CLI_GUIDE.md)

## Agent Integration

This project includes:

- Agent-friendly HTTP API endpoints under `/api/v1/...`
- Swagger UI at `/api/docs`
- OpenAPI spec at `/api/openapi.json`
- CLI wrapper at `python3 cli.py`
- End-to-end API test script at `python3 scripts/e2e_api_test.py`
- In-browser SRT subtitle editing and subtitle-burned MP4 generation from the video list
- Burned subtitle styling with configurable font family, size, colors, outline, spacing, margins, and translucent background
- Remote STT deployment support where the web app uploads MP4 files to Whisper and syncs transcript artifacts back
