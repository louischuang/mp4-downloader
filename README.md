# YouTube to MP4 Downloader

這是一個本機執行或用 Docker 部署的小工具，貼上 YouTube 影片網址後，就能下載成 MP4 檔案。

## 注意事項

- 請只下載你有權限保存的內容。
- 使用前請自行確認是否符合 YouTube 條款、影片授權與著作權規範。

## 需求

- Python 3.14 以上
- `yt-dlp`
- `ffmpeg`（可選，但建議安裝，能讓高畫質影片與音訊合併輸出成 MP4）

## 安裝

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你想要高畫質合併輸出，macOS 可另外安裝：

```bash
brew install ffmpeg
```

## Docker 啟動

專案已包含 `Dockerfile` 與 `docker-compose.yml`，容器內已安裝 `ffmpeg` 與 `nodejs`，可支援較完整的 MP4 合併輸出與 YouTube JavaScript 解析。

```bash
docker-compose up --build -d
```

如果你的 Docker 是新版 Compose plugin，也可以用：

```bash
docker compose up --build -d
```

啟動後可在瀏覽器開啟：

```text
http://127.0.0.1:5001
```

### 永久保存 MP4 檔案

- `docker-compose.yml` 已把主機上的 `./video-storage` 掛載到容器內的 `/data/downloads`
- 所有下載完成的 MP4 都會留在主機的 `video-storage/` 資料夾
- 就算容器刪掉重建，影片檔案仍會保留

### YouTube cookies 設定

若出現 `Sign in to confirm you're not a bot`，代表 YouTube 要求登入驗證。這時請把你匯出的 cookies 檔放到專案的 `cookies/youtube.txt`。

- 主機路徑：`./cookies/youtube.txt`
- 容器路徑：`/data/cookies/youtube.txt`
- `docker-compose.yml` 已自動掛載成唯讀
- 程式會先把 cookies 複製到容器內可寫的暫存位置，再交給 `yt-dlp` 使用

建議使用瀏覽器外掛把已登入 YouTube 的 cookies 匯出成 Netscape 格式文字檔，再命名成 `youtube.txt`。

如果你想改成別的外部路徑，可以把：

```yaml
volumes:
  - ./video-storage:/data/downloads
```

改成例如：

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
```

## 啟動

```bash
python3 app.py
```

啟動後打開瀏覽器進入：

```text
http://127.0.0.1:5000
```

## 功能說明

- 支援一般 YouTube `watch` 網址
- 支援 `youtu.be` 短網址
- 支援 `shorts` 網址
- 下載完成後可直接點按鈕取得檔案
- 可透過 `DOWNLOADS_DIR` 環境變數指定下載資料夾
- Docker 預設會存放在主機的 `video-storage/` 資料夾
- Docker 預設會從 `cookies/youtube.txt` 讀取 YouTube cookies
- Docker 預設會啟用 `YTDLP_REMOTE_COMPONENTS=ejs:github`

## 補充

- 若系統沒有 `ffmpeg`，程式會先嘗試抓可直接下載的 MP4 格式。
- 若遇到某些影片只有分離式影音串流，安裝 `ffmpeg` 後成功率和畫質通常會更好。
- Docker 版本已內建 `ffmpeg` 與 `nodejs`，因此更適合直接部署使用。
- 若 YouTube 要求 bot 驗證，通常仍需要 cookies 才能成功下載。
