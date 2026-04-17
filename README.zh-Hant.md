# YouTube to MP4 Downloader

這是一個可在本機或 Docker 上運行的 YouTube 下載與影音轉文字工具，支援：

- Docker 部署
- MP4 永久儲存
- 影片轉文字
- 畫質選擇
- 即時下載進度
- 繁中、簡中、英文、日文介面

> 請只下載你有權限保存的內容，並自行遵守 YouTube 條款與著作權規範。

## 預覽

![App preview](assets/app-preview.svg)

## 功能特色

- 支援 YouTube `watch`、`youtu.be`、`shorts`、`embed` 網址
- 可選擇下載畫質：`最佳可用畫質`、`1080p`、`720p`、`360p`
- 可使用 `開始下載` 或 `下載與轉成文字`
- 可切換 `YouTube 下載` 與 `上傳 MP4` 頁籤
- 可上傳本機 MP4 並自訂影片標題
- 上傳完成後會自動開始進行轉文字
- 下載時可看到即時進度與狀態文字，完成後只保留完成彈窗
- 影片列表可播放本機 MP4、開啟原始 YouTube 網址、下載 MP4 或字幕檔
- 支援本機 `faster-whisper` 轉文字，輸出 `txt`、`srt`、`vtt`、`json`
- 轉文字進度會顯示在各自影片列內，不與下載進度共用
- 最新加入的影片會在標題前顯示紅色 `NEW` 標記
- 安裝 `ffmpeg` 時可輸出合併後的 MP4
- 可從右上角按鈕列切換語言
- 可將下載影片持久化儲存在容器外
- 支援掛入 YouTube cookies 處理登入或反機器人驗證
- 提供可供其他平台或 AI Agent 使用的 HTTP API
- 提供 Swagger UI 與 OpenAPI JSON 文件
- 提供 `python3 cli.py` CLI 介面
- 提供 `python3 scripts/e2e_api_test.py` 端對端測試腳本

## 技術組成

- Python `Flask`
- `yt-dlp`
- `faster-whisper`
- `ffmpeg`
- `nodejs`，用於 YouTube JavaScript runtime 解析
- Docker / Docker Compose

## Docker 快速啟動

此專案已內建：

- `Dockerfile`
- `docker-compose.yml`
- 永久儲存映射
- cookies 掛載設定
- STT 獨立服務容器

啟動方式：

```bash
docker-compose up --build -d
```

如果你的環境使用新版 Compose plugin：

```bash
docker compose up --build -d
```

啟動後請打開：

```text
http://127.0.0.1:5001
```

## 永久儲存資料夾

下載完成的 MP4、轉錄結果與模型快取會透過以下 bind mount 儲存在主機：

```yaml
volumes:
  - ./video-storage:/data/downloads
  - ./transcripts:/data/output
  - ./models:/models/huggingface
```

這表示：

- container 重啟後影片仍然保留
- container 重建後影片仍然保留
- 影片、字幕與模型不會只存在容器內部檔案系統

如果你想改成其他主機路徑，例如：

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
```

轉文字輸出預設會放在：

```text
./transcripts
```

Whisper 模型快取預設會放在：

```text
./models
```

## YouTube Cookies 設定

如果 YouTube 出現 `Sign in to confirm you're not a bot` 之類的訊息，請先匯出 YouTube cookies 的 Netscape 格式檔案，放到：

```text
./cookies/youtube.txt
```

Docker 會將這個檔案掛載到：

```text
/data/cookies/youtube.txt
```

補充：

- compose 會將 cookies 目錄掛成唯讀
- 程式會先把 cookies 複製到容器內可寫入的暫存位置，再交給 `yt-dlp`
- container 也會預設啟用 `YTDLP_REMOTE_COMPONENTS=ejs:github`

## Agent API 與 Swagger

此專案提供可給其他平台或 AI Agent 串接的 API：

- `GET /api/health`
- `GET /api/capabilities`
- `POST /api/v1/downloads`
- `POST /api/v1/uploads`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/videos`
- `POST /api/v1/transcriptions`
- `GET /api/v1/transcriptions/{job_id}`

相關文件：

- Swagger UI：`/api/docs`
- OpenAPI JSON：`/api/openapi.json`
- 詳細說明：[docs/AGENT_API.md](docs/AGENT_API.md)

## CLI

範例：

```bash
python3 cli.py health
python3 cli.py capabilities --json
python3 cli.py videos --json
python3 cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --wait --json
python3 cli.py transcribe "example-video.mp4" --wait --json
```

## 端對端測試腳本

完整驗證 API 流程：

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM"
```

若只想看摘要：

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM" --summary-only
```

## 本機開發

如果你想不透過 Docker 直接執行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

然後打開：

```text
http://127.0.0.1:5000
```

macOS 若要更完整支援 MP4 合併，可另外安裝：

```bash
brew install ffmpeg
```

## 專案結構

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

## 使用方式

1. 在瀏覽器打開服務頁面。
2. 選擇 `YouTube 下載` 或 `上傳 MP4`。
3. 若使用 YouTube 模式，貼上影片網址並選擇畫質。
4. 若使用上傳模式，選擇本機 MP4 並輸入影片標題。
5. 按下當前模式的主要按鈕。
6. 在畫面上查看即時下載或轉錄進度。
7. 若選擇轉文字，或是使用 MP4 上傳模式，完成後會自動接續 STT 工作。
8. 完成後可在下方影片列表中：
   - 播放影片
   - 開啟原始 YouTube 網址
   - 下載 MP4
   - 下載 `txt` / `srt` / `vtt` / `json`
   - 重新轉文字

## 補充說明

- 如果沒有 `ffmpeg`，程式會退回可直接下載的格式。
- 如果有 `ffmpeg`，可將分離式影音串流合併為 MP4。
- 第一次執行 `faster-whisper` 時，會先下載模型到 `./models`，之後同模型會直接使用快取。
- 某些影片仍可能因帳號、區域、年齡限制或反機器人驗證而需要有效 cookies。

## 授權

本專案採用 MIT License，詳見 [LICENSE](LICENSE)。
