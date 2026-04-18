# YouTube to MP4 Downloader

这是一个可在本机或 Docker 上运行的 YouTube 下载与影音转文字工具，支持：

- Docker 部署
- MP4 与字幕永久存储
- `faster-whisper` 转文字
- 画质选择
- 实时下载与转录进度
- 繁中、简中、英文、日文界面
- HTTP API、Swagger 文档、CLI 与端到端测试脚本

> 请只下载你有权限保存的内容，并自行遵守 YouTube 条款与著作权规范。

## 预览

![App preview](assets/app-preview.svg)

## 功能特色

- 支持 YouTube `watch`、`youtu.be`、`shorts`、`embed` 链接
- 可选择下载画质：`最佳可用画质`、`1080p`、`720p`、`360p`
- 可使用 `开始下载` 或 `下载与转成文字`
- 可切换 `YouTube 下载` 与 `上传 MP4` 标签
- 可上传本地 MP4 并自定义视频标题
- 上传完成后会自动开始进行转文字
- 下载与转录时可看到实时进度与状态文字
- 可播放本地 MP4、打开原始 YouTube 页面、下载生成文件
- 支持本机 `faster-whisper` 转文字，输出 `txt`、`srt`、`vtt`、`json`
- 可直接在浏览器中编辑生成的 `srt` 字幕
- 可从视频列表工具栏生成烧录字幕的新 MP4
- 可自定义烧录字幕的字体、字级、字色、外框、行距、边距与透明背景样式
- 安装 `ffmpeg` 时可输出合并后的 MP4
- 可从右上角按钮栏切换语言
- 可将下载视频、字幕和模型缓存持久化存储在容器外
- 支持挂载 YouTube cookies 处理登录或反机器人验证
- 提供可供其他平台或 AI Agent 使用的 HTTP API
- 提供 Swagger UI 与 OpenAPI JSON 文档
- 提供 `python3 cli.py` CLI 接口
- 提供 `python3 scripts/e2e_api_test.py` 端到端测试脚本

## 技术组成

- Python `Flask`
- `yt-dlp`
- `faster-whisper`
- `ffmpeg`
- `nodejs`，用于 YouTube JavaScript runtime 解析
- Docker / Docker Compose

## Docker 快速启动

此项目已内建：

- `Dockerfile`
- `docker-compose.yml`
- 永久存储映射
- cookies 挂载设置
- STT 独立服务容器

启动方式：

```bash
docker-compose up --build -d
```

如果你的环境使用新版 Compose plugin：

```bash
docker compose up --build -d
```

启动后请打开：

```text
http://127.0.0.1:5001
```

Swagger UI：

```text
http://127.0.0.1:5001/api/docs
```

## 永久存储

下载完成的 MP4、转录结果与模型缓存会通过以下 bind mount 存储在主机：

```yaml
volumes:
  - ./video-storage:/data/downloads
  - ./transcripts:/data/output
  - ./models:/models/huggingface
```

这表示：

- container 重启后视频仍然保留
- container 重建后视频仍然保留
- 视频、字幕与模型不会只存在容器内部文件系统

如果你想改成其他主机路径，例如：

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
```

转文字输出默认放在：

```text
./transcripts
```

Whisper 模型缓存默认放在：

```text
./models
```

## YouTube Cookies 设置

如果 YouTube 出现 `Sign in to confirm you're not a bot` 之类的消息，请先导出 YouTube cookies 的 Netscape 格式文件，放到：

```text
./cookies/youtube.txt
```

Docker 会将这个文件挂载到：

```text
/data/cookies/youtube.txt
```

补充：

- compose 会将 cookies 目录挂成只读
- 程序会先把 cookies 复制到容器内可写入的临时位置，再交给 `yt-dlp`
- container 也会默认启用 `YTDLP_REMOTE_COMPONENTS=ejs:github`

## Agent API 与 Swagger

此项目提供可供其他平台或 AI Agent 调用的 API：

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

`POST /api/v1/burned-videos` 可传入 `style` 对象，自定义烧录字幕字体设置，包含：

- `size`、`font_family`
- `text_color`、`outline_color`、`outline_width`
- `position`、`line_spacing`
- `margin_v`、`margin_l`、`margin_r`
- `shadow`
- `background`、`background_color`、`background_opacity`、`background_size`、`background_radius`
- `max_chars_per_line`

相关文档：

- Swagger UI：`/api/docs`
- OpenAPI JSON：`/api/openapi.json`
- 详细说明：[docs/AGENT_API.md](docs/AGENT_API.md)
- 工具使用说明：[docs/TOOL_USAGE.md](docs/TOOL_USAGE.md)
- CLI 使用说明：[docs/CLI_GUIDE.md](docs/CLI_GUIDE.md)

## CLI

示例：

```bash
python3 cli.py health
python3 cli.py capabilities --json
python3 cli.py videos --json
python3 cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --wait --json
python3 cli.py transcribe "example-video.mp4" --wait --json
python3 cli.py burn "example-video.mp4" --wait --size plus_20 --font-family sans --text-color "#ffffff" --outline-color "#000000" --background --background-color "#000000" --background-opacity 48 --background-size 24 --background-radius 18
```

## 端到端测试脚本

完整验证 API 流程：

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM"
```

若只想看摘要：

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM" --summary-only
```

## 本地开发

如果你想不通过 Docker 直接运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

然后打开：

```text
http://127.0.0.1:5000
```

macOS 若要更完整支持 MP4 合并，可另外安装：

```bash
brew install ffmpeg
```

## 项目结构

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

1. 在浏览器打开服务页面。
2. 选择 `YouTube 下载` 或 `上传 MP4`。
3. 若使用 YouTube 模式，粘贴视频链接并选择画质。
4. 若使用上传模式，选择本地 MP4 并输入视频标题。
5. 点击当前模式的主要按钮。
6. 在页面上查看实时下载或转录进度。
7. 如果启用了转文字，或是使用 MP4 上传模式，完成后会自动接续 STT 作业。
8. 完成后可在影片列表中播放视频、打开原始链接、下载 MP4，或下载 `txt` / `srt` / `vtt` / `json`。
9. 如果字幕内容需要修正，可使用 `编辑字幕` 直接修改 `srt` 并保存。
10. 保存字幕后，可使用 `生成烧录 MP4` 重新导出带字幕的新视频。

## 补充说明

- 如果没有 `ffmpeg`，程序会退回可直接下载的格式。
- 如果有 `ffmpeg`，可将分离式音视频流合并为 MP4。
- 烧录字幕 MP4 也需要 `ffmpeg` 才能使用。
- 第一次执行 `faster-whisper` 时会先下载模型到 `./models`，之后会直接使用缓存。
- 某些视频仍可能因为账号、地区、年龄限制或反机器人验证而需要有效 cookies。

## 授权

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
