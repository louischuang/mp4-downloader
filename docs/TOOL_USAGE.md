# 工具使用說明

這個工具提供三種主要使用方式：

1. 用網頁下載 YouTube 影片並轉成 MP4
2. 上傳本機 MP4 後自動轉文字
3. 編輯字幕並產生燒錄字幕的新 MP4

## 網頁入口

- 主頁：`http://127.0.0.1:5001`
- Swagger 文件：`http://127.0.0.1:5001/api/docs`

## YouTube 下載流程

1. 打開首頁
2. 保持在 `YouTube 下載` 頁籤
3. 貼上 YouTube 網址
4. 選擇下載畫質
5. 點 `開始下載`，或點 `下載與轉成文字`
6. 等待進度完成
7. 在下方影片列表中播放、下載或繼續轉錄

## 上傳 MP4 流程

1. 切到 `上傳 MP4`
2. 輸入影片標題
3. 選擇本機 MP4 檔案
4. 點 `上傳並轉成文字`
5. 系統會自動建立轉錄工作
6. 完成後影片會出現在下方列表

## 字幕編輯與燒錄流程

1. 在影片列表中找到目標影片
2. 點 `編輯字幕`
3. 修改 `SRT` 內容後儲存
4. 點 `產生燒錄 MP4`
5. 在彈窗中設定：
   - 字型家族
   - 字級
   - 字體顏色
   - 外框顏色與寬度
   - 字幕位置
   - 行距
   - 上下左右邊距
   - 背景顏色、透明度、大小、圓角
6. 開始燒錄後，新的影片會出現在列表

## 影片列表可做的操作

- 播放影片
- 開啟原始 YouTube 網址
- 下載 MP4
- 下載 `txt`、`srt`、`vtt`、`json`
- 重新轉文字
- 刪除影片與相關字幕檔

## API 能力

這個工具也提供 API 給其他平台或 AI Agent 使用：

- `GET /api/health`
- `GET /api/capabilities`
- `POST /api/v1/downloads`
- `POST /api/v1/uploads`
- `GET /api/v1/videos`
- `POST /api/v1/transcriptions`
- `POST /api/v1/burned-videos`
- `GET /api/v1/subtitles/{filename}`
- `PUT /api/v1/subtitles/{filename}`

詳細 API 說明請看 [AGENT_API.md](./AGENT_API.md)。
