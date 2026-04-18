# CLI 使用說明

這個專案提供 `python3 cli.py` 指令列工具，方便其他平台、腳本與 AI Agent 呼叫。

## 基本格式

```bash
python3 cli.py [--base-url URL] [--json] <command> [options]
```

全域選項：

- `--base-url`：指定 API 位置，預設是 `http://127.0.0.1:5000`
- `--json`：用 JSON 格式輸出結果

## 可用指令

### 健康檢查

```bash
python3 cli.py health
```

### 取得能力列表

```bash
python3 cli.py capabilities --json
```

### 取得影片列表

```bash
python3 cli.py videos --json
```

### 建立下載工作

```bash
python3 cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --quality 720p --wait --json
```

常用參數：

- `--quality`: `best`、`1080p`、`720p`、`360p`
- `--wait`: 等待工作完成
- `--interval`: 輪詢秒數
- `--timeout`: 逾時秒數
- `--transcribe`: 下載完成後直接轉文字
- `--model`: `small` 或 `medium`

### 查詢下載工作

```bash
python3 cli.py job <download-job-id> --json
```

### 建立轉錄工作

```bash
python3 cli.py transcribe "example-video.mp4" --model small --wait --json
```

### 查詢轉錄工作

```bash
python3 cli.py transcription-status <transcription-job-id> --json
```

### 產生燒錄字幕 MP4

```bash
python3 cli.py burn "example-video.mp4" \
  --wait \
  --size plus_20 \
  --font-family sans \
  --text-color "#ffffff" \
  --outline-color "#000000" \
  --outline-width 1.2 \
  --position bottom \
  --line-spacing 2 \
  --margin-v 34 \
  --margin-l 42 \
  --margin-r 42 \
  --background \
  --background-color "#000000" \
  --background-opacity 48 \
  --background-size 24 \
  --background-radius 18 \
  --max-chars-per-line 18 \
  --json
```

燒錄樣式參數：

- `--size`: `minus_20`、`minus_10`、`zero`、`plus_10`、`plus_20`、`plus_30`
- `--font-family`: `sans`、`serif`、`mono`
- `--text-color`
- `--outline-color`
- `--outline-width`
- `--position`: `bottom`、`middle`、`top`
- `--line-spacing`
- `--margin-v`
- `--margin-l`
- `--margin-r`
- `--shadow`
- `--background`
- `--background-color`
- `--background-opacity`
- `--background-size`
- `--background-radius`
- `--max-chars-per-line`

## 建議流程

1. `health`
2. `capabilities`
3. `download`
4. `transcribe`
5. 視需要編輯字幕
6. `burn`

如果要搭配其他 Agent 使用，建議加上 `--json`，讓回傳結果更容易解析。
