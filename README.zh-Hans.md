# YouTube to MP4 Downloader

这是一个可在本机或 Docker 上运行的 YouTube 下载工具，支持：

- Docker 部署
- MP4 永久存储
- 画质选择
- 实时下载进度
- 繁中、简中、英文、日文界面

> 请只下载你有权限保存的内容，并自行遵守 YouTube 条款与著作权规范。

## 预览

![App preview](assets/app-preview.svg)

## 功能特色

- 支持 YouTube `watch`、`youtu.be`、`shorts`、`embed` 链接
- 可选择下载画质：`最佳可用画质`、`1080p`、`720p`、`360p`
- 下载时可看到实时进度与状态文字
- 安装 `ffmpeg` 时可输出合并后的 MP4
- 可从右上角按钮栏切换语言
- 可将下载视频持久化存储在容器外
- 支持挂载 YouTube cookies 处理登录或反机器人验证

## 技术组成

- Python `Flask`
- `yt-dlp`
- `ffmpeg`
- `nodejs`，用于 YouTube JavaScript runtime 解析
- Docker / Docker Compose

## Docker 快速启动

此项目已内建：

- `Dockerfile`
- `docker-compose.yml`
- 永久存储映射
- cookies 挂载设置

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

## 永久存储 MP4

下载完成的 MP4 会通过以下 bind mount 存储在主机：

```yaml
volumes:
  - ./video-storage:/data/downloads
```

这表示：

- container 重启后视频仍然保留
- container 重建后视频仍然保留
- 视频不会只存在容器内部文件系统

如果你想改成其他主机路径，例如：

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
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
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
├── templates/
├── assets/
├── cookies/
└── video-storage/
```

## 使用方式

1. 在浏览器打开服务页面。
2. 粘贴 YouTube 视频链接。
3. 选择你要的画质。
4. 点击下载按钮。
5. 在页面上查看实时进度与状态文字。
6. 下载完成后，从完成区块下载 MP4 文件。

## 补充说明

- 如果没有 `ffmpeg`，程序会退回可直接下载的格式。
- 如果有 `ffmpeg`，可将分离式音视频流合并为 MP4。
- 某些视频仍可能因为账号、地区、年龄限制或反机器人验证而需要有效 cookies。

## 授权

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
