# Project Status Summary

## 專案名稱

YouTube to MP4 Downloader

## 專案目的

這個專案目前是一套可在本機或 Docker 環境運行的工具，提供以下完整流程：

1. 貼上 YouTube 影片網址
2. 下載 MP4 影片
3. 依需求自動接續本地語音轉文字
4. 保存影片、字幕與模型快取
5. 在前端列表中播放、驗證與下載結果

> 使用時仍需自行遵守 YouTube 條款與著作權規範，只下載有權限保存的內容。

## 目前架構

目前為雙服務 Docker 架構：

- `youtube-to-mp4`
  - Flask 主服務
  - 負責 YouTube 下載、前端頁面、影片清單、下載任務與 STT 任務代理
- `youtube-to-mp4-stt`
  - 獨立的 `faster-whisper` STT 服務
  - 負責讀取已下載 MP4、執行語音轉文字、輸出字幕與文字檔

## 主要技術

- Python `Flask`
- `yt-dlp`
- `ffmpeg`
- `nodejs`
- `faster-whisper`
- Docker / Docker Compose

## 目前已完成功能

### 下載功能

- 支援 YouTube `watch`、`youtu.be`、`shorts`、`embed` 網址
- 可選擇下載畫質：
  - 最佳可用畫質
  - 1080p
  - 720p
  - 360p
- 可選擇：
  - `開始下載`
  - `下載與轉成文字`
- 顯示下載進度與狀態文字
- 下載完成後顯示完成彈窗

### 影音轉文字功能

- 使用獨立 STT container 執行本地轉錄
- 目前支援 `faster-whisper`
- 可輸出：
  - `txt`
  - `srt`
  - `vtt`
  - `json`
- 每支影片有獨立的轉文字進度條
- 已轉換影片可重新觸發一次轉文字

### 影片清單功能

- 下載完成的影片會顯示於列表中
- 最新加入的影片標題前顯示紅色 `NEW`
- 每列支援圖示操作：
  - 播放影片
  - 開啟原始 YouTube 網址
  - 開啟下載視窗
  - 轉文字
  - 重新轉文字
- 若已有字幕，可在播放器中掛入字幕驗證

### 多語系功能

- 繁體中文
- 簡體中文
- English
- 日本語

桌機版右上角為按鈕列，手機窄版為圖示展開式選單。

## 資料持久化目錄

目前透過 Docker volume / bind mount 保存以下資料：

- `./video-storage`
  - 保存下載後的 MP4
- `./transcripts`
  - 保存轉錄結果
- `./models`
  - 保存 `faster-whisper` 模型快取
- `./cookies`
  - 保存 YouTube cookies 檔案

## 重要檔案

- `/Users/louischuang/CompanyStorage/嵐奕科技有限公司/第四處 技術處/正在進行中的專案/20260417-YoutubeToMP4/YoutubeToMp4/app.py`
  - Flask 主程式
- `/Users/louischuang/CompanyStorage/嵐奕科技有限公司/第四處 技術處/正在進行中的專案/20260417-YoutubeToMP4/YoutubeToMp4/templates/index.html`
  - 前端頁面與主要互動邏輯
- `/Users/louischuang/CompanyStorage/嵐奕科技有限公司/第四處 技術處/正在進行中的專案/20260417-YoutubeToMP4/YoutubeToMp4/static/style.css`
  - 前端樣式
- `/Users/louischuang/CompanyStorage/嵐奕科技有限公司/第四處 技術處/正在進行中的專案/20260417-YoutubeToMP4/YoutubeToMp4/docker-compose.yml`
  - 雙容器啟動設定
- `/Users/louischuang/CompanyStorage/嵐奕科技有限公司/第四處 技術處/正在進行中的專案/20260417-YoutubeToMP4/YoutubeToMp4/docker/stt/server.py`
  - STT 服務
- `/Users/louischuang/CompanyStorage/嵐奕科技有限公司/第四處 技術處/正在進行中的專案/20260417-YoutubeToMP4/YoutubeToMp4/docs/STT_IMPLEMENTATION_PLAN.md`
  - STT 實作規劃文件

## 目前運行方式

使用 Docker：

```bash
docker-compose up --build -d
```

服務預設入口：

```text
http://127.0.0.1:5001
```

## 目前已知狀態

- Docker 版主流程已可正常使用
- 下載完成後不再於頁尾額外顯示完成結果區塊
- 最新影片會顯示 `NEW`
- 第一次使用 STT 時，模型會先下載到 `./models`
- STT 目前已採獨立容器，之後可切換到不同硬體環境

## 下一步可延伸方向

可優先考慮的下一階段工作：

1. 補齊其他語系 README，同步最新功能描述
2. 增加轉錄語言選項與自動偵測設定
3. 增加轉錄歷史、搜尋與篩選
4. 將影片與轉錄 metadata 從 JSON 索引升級為資料庫
5. 為未來 NVIDIA GPU 環境接入 `x64 + CUDA` 的 STT 部署版本
6. 增加登入保護或使用權限控管

## Repo 狀態

- GitHub repository:
  - [https://github.com/louischuang/mp4-downloader](https://github.com/louischuang/mp4-downloader)
- 目前最新已推送 commit：
  - `5e51841`
- 最新 commit message：
  - `Refine video list UI and update README`
