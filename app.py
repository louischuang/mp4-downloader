from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", str(BASE_DIR / "downloads"))).resolve()
DOWNLOADS_DIR.mkdir(exist_ok=True)
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "5000"))
APP_DEBUG = os.getenv("APP_DEBUG", "false").lower() == "true"
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", "").strip()
YTDLP_REMOTE_COMPONENTS = os.getenv("YTDLP_REMOTE_COMPONENTS", "ejs:github").strip()

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

app = Flask(__name__)
jobs_lock = threading.Lock()
download_jobs: dict[str, dict[str, Any]] = {}
QUALITY_OPTIONS = {
    "best": {
        "label_key": "quality.best",
        "ffmpeg_format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "direct_format": "b[ext=mp4]/bv*[ext=mp4]+ba[ext=m4a]/b",
    },
    "1080p": {
        "label_key": "quality.1080p",
        "ffmpeg_format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b[height<=1080]/b",
        "direct_format": "b[height<=1080][ext=mp4]/b[height<=1080]/b",
    },
    "720p": {
        "label_key": "quality.720p",
        "ffmpeg_format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]/b",
        "direct_format": "b[height<=720][ext=mp4]/b[height<=720]/b",
    },
    "360p": {
        "label_key": "quality.360p",
        "ffmpeg_format": "bv*[height<=360][ext=mp4]+ba[ext=m4a]/b[height<=360][ext=mp4]/b[height<=360]/b",
        "direct_format": "b[height<=360][ext=mp4]/b[height<=360]/b",
    },
}
TRANSLATIONS = {
    "zh-Hant": {
        "app.title": "YouTube to MP4 Downloader",
        "hero.eyebrow": "Local Utility",
        "hero.title": "貼上 YouTube 連結，直接下載 MP4",
        "hero.intro": "這是一個本機執行的小工具。輸入影片網址後，後端會呼叫 yt-dlp 將影片抓回你的電腦。",
        "lang.label": "語言",
        "lang.zh-Hant": "繁中",
        "lang.zh-Hans": "简中",
        "lang.en": "English",
        "lang.ja": "日本語",
        "status.ytdlp": "yt-dlp",
        "status.ffmpeg": "ffmpeg",
        "status.ready": "已就緒",
        "status.missing": "未安裝",
        "status.optional": "可選安裝",
        "form.url": "YouTube 影片網址",
        "form.url_placeholder": "https://www.youtube.com/watch?v=...",
        "form.submit": "開始下載",
        "form.quality": "下載畫質",
        "tip.copyright": "請只下載你有權限保存的內容，並自行遵守 YouTube 條款與著作權規範。",
        "progress.kicker": "下載進度",
        "progress.waiting": "等待下載開始",
        "progress.creating_job": "正在建立下載工作",
        "progress.preparing": "正在準備下載",
        "progress.fetching_info": "正在擷取影片資訊",
        "progress.analyzing_formats": "正在分析可用格式",
        "progress.parsing_auth": "正在解析 YouTube 驗證資訊",
        "progress.merging_mp4": "正在合併影音為 MP4",
        "progress.using_existing": "檔案已存在，直接使用現有輸出",
        "progress.completed": "下載完成",
        "progress.failed": "下載失敗",
        "progress.processing": "正在處理下載工作",
        "result.completed": "下載完成：",
        "result.quality": "畫質：",
        "result.download": "下載檔案",
        "quality.best": "最佳可用畫質",
        "quality.1080p": "1080p",
        "quality.720p": "720p",
        "quality.360p": "360p",
        "error.empty_url": "請先貼上 YouTube 影片網址。",
        "error.invalid_url": "請輸入有效的 YouTube 影片網址。",
        "error.job_not_found": "找不到這個下載工作。",
        "error.start_download": "無法啟動下載。",
        "error.fetch_status": "無法取得下載狀態。",
        "error.download_failed": "下載失敗，請稍後再試。",
        "error.output_missing": "影片已完成，但找不到輸出檔案。",
        "warning.no_ffmpeg": "目前系統尚未安裝 ffmpeg，所以會優先下載可直接取得的 mp4 版本。",
        "warning.no_node": "目前系統尚未安裝 nodejs，YouTube 某些格式可能會抓不完整。",
        "warning.no_cookies": "若遇到 YouTube 要求登入驗證，請掛入 cookies 檔案。",
    },
    "zh-Hans": {
        "app.title": "YouTube to MP4 Downloader",
        "hero.eyebrow": "Local Utility",
        "hero.title": "粘贴 YouTube 链接，直接下载 MP4",
        "hero.intro": "这是一个本机运行的小工具。输入视频网址后，后端会调用 yt-dlp 将视频抓回你的电脑。",
        "lang.label": "语言",
        "lang.zh-Hant": "繁中",
        "lang.zh-Hans": "简中",
        "lang.en": "English",
        "lang.ja": "日本語",
        "status.ytdlp": "yt-dlp",
        "status.ffmpeg": "ffmpeg",
        "status.ready": "已就绪",
        "status.missing": "未安装",
        "status.optional": "可选安装",
        "form.url": "YouTube 视频网址",
        "form.url_placeholder": "https://www.youtube.com/watch?v=...",
        "form.submit": "开始下载",
        "form.quality": "下载画质",
        "tip.copyright": "请只下载你有权限保存的内容，并自行遵守 YouTube 条款与著作权规范。",
        "progress.kicker": "下载进度",
        "progress.waiting": "等待下载开始",
        "progress.creating_job": "正在创建下载任务",
        "progress.preparing": "正在准备下载",
        "progress.fetching_info": "正在获取视频信息",
        "progress.analyzing_formats": "正在分析可用格式",
        "progress.parsing_auth": "正在解析 YouTube 验证信息",
        "progress.merging_mp4": "正在合并音视频为 MP4",
        "progress.using_existing": "文件已存在，直接使用现有输出",
        "progress.completed": "下载完成",
        "progress.failed": "下载失败",
        "progress.processing": "正在处理下载任务",
        "result.completed": "下载完成：",
        "result.quality": "画质：",
        "result.download": "下载文件",
        "quality.best": "最佳可用画质",
        "quality.1080p": "1080p",
        "quality.720p": "720p",
        "quality.360p": "360p",
        "error.empty_url": "请先粘贴 YouTube 视频网址。",
        "error.invalid_url": "请输入有效的 YouTube 视频网址。",
        "error.job_not_found": "找不到这个下载任务。",
        "error.start_download": "无法启动下载。",
        "error.fetch_status": "无法取得下载状态。",
        "error.download_failed": "下载失败，请稍后再试。",
        "error.output_missing": "视频已完成，但找不到输出文件。",
        "warning.no_ffmpeg": "当前系统尚未安装 ffmpeg，因此会优先下载可直接取得的 mp4 版本。",
        "warning.no_node": "当前系统尚未安装 nodejs，YouTube 某些格式可能无法完整抓取。",
        "warning.no_cookies": "若遇到 YouTube 要求登录验证，请挂载 cookies 文件。",
    },
    "en": {
        "app.title": "YouTube to MP4 Downloader",
        "hero.eyebrow": "Local Utility",
        "hero.title": "Paste a YouTube link and download MP4",
        "hero.intro": "This is a local utility. After you enter a video URL, the backend uses yt-dlp to download it to your computer.",
        "lang.label": "Language",
        "lang.zh-Hant": "繁中",
        "lang.zh-Hans": "简中",
        "lang.en": "English",
        "lang.ja": "日本語",
        "status.ytdlp": "yt-dlp",
        "status.ffmpeg": "ffmpeg",
        "status.ready": "Ready",
        "status.missing": "Missing",
        "status.optional": "Optional",
        "form.url": "YouTube Video URL",
        "form.url_placeholder": "https://www.youtube.com/watch?v=...",
        "form.submit": "Download",
        "form.quality": "Quality",
        "tip.copyright": "Download only content you are allowed to save, and make sure you comply with YouTube terms and copyright rules.",
        "progress.kicker": "Download Progress",
        "progress.waiting": "Waiting to start",
        "progress.creating_job": "Creating download job",
        "progress.preparing": "Preparing download",
        "progress.fetching_info": "Fetching video information",
        "progress.analyzing_formats": "Analyzing available formats",
        "progress.parsing_auth": "Parsing YouTube verification details",
        "progress.merging_mp4": "Merging audio and video into MP4",
        "progress.using_existing": "File already exists, using current output",
        "progress.completed": "Download completed",
        "progress.failed": "Download failed",
        "progress.processing": "Processing download job",
        "result.completed": "Download completed:",
        "result.quality": "Quality:",
        "result.download": "Download file",
        "quality.best": "Best available",
        "quality.1080p": "1080p",
        "quality.720p": "720p",
        "quality.360p": "360p",
        "error.empty_url": "Please paste a YouTube video URL first.",
        "error.invalid_url": "Please enter a valid YouTube video URL.",
        "error.job_not_found": "Download job not found.",
        "error.start_download": "Unable to start the download.",
        "error.fetch_status": "Unable to fetch download status.",
        "error.download_failed": "Download failed. Please try again later.",
        "error.output_missing": "The video finished, but the output file could not be found.",
        "warning.no_ffmpeg": "ffmpeg is not installed, so the app will prioritize MP4 formats that can be downloaded directly.",
        "warning.no_node": "nodejs is not installed, so some YouTube formats may be incomplete.",
        "warning.no_cookies": "If YouTube asks for sign-in verification, mount a cookies file.",
    },
    "ja": {
        "app.title": "YouTube to MP4 Downloader",
        "hero.eyebrow": "Local Utility",
        "hero.title": "YouTube リンクを貼り付けて MP4 をダウンロード",
        "hero.intro": "これはローカルで動く小さなツールです。動画 URL を入力すると、バックエンドが yt-dlp を使って動画を保存します。",
        "lang.label": "言語",
        "lang.zh-Hant": "繁中",
        "lang.zh-Hans": "简中",
        "lang.en": "English",
        "lang.ja": "日本語",
        "status.ytdlp": "yt-dlp",
        "status.ffmpeg": "ffmpeg",
        "status.ready": "準備完了",
        "status.missing": "未インストール",
        "status.optional": "任意",
        "form.url": "YouTube 動画 URL",
        "form.url_placeholder": "https://www.youtube.com/watch?v=...",
        "form.submit": "ダウンロード開始",
        "form.quality": "画質",
        "tip.copyright": "保存権限のあるコンテンツのみをダウンロードし、YouTube の利用規約と著作権ルールを守ってください。",
        "progress.kicker": "ダウンロード進捗",
        "progress.waiting": "開始待ち",
        "progress.creating_job": "ダウンロードジョブを作成中",
        "progress.preparing": "ダウンロードを準備中",
        "progress.fetching_info": "動画情報を取得中",
        "progress.analyzing_formats": "利用可能な形式を解析中",
        "progress.parsing_auth": "YouTube 認証情報を解析中",
        "progress.merging_mp4": "音声と映像を MP4 に結合中",
        "progress.using_existing": "既存ファイルを使用します",
        "progress.completed": "ダウンロード完了",
        "progress.failed": "ダウンロード失敗",
        "progress.processing": "ダウンロード処理中",
        "result.completed": "ダウンロード完了：",
        "result.quality": "画質：",
        "result.download": "ファイルをダウンロード",
        "quality.best": "最良の画質",
        "quality.1080p": "1080p",
        "quality.720p": "720p",
        "quality.360p": "360p",
        "error.empty_url": "先に YouTube 動画 URL を貼り付けてください。",
        "error.invalid_url": "有効な YouTube 動画 URL を入力してください。",
        "error.job_not_found": "ダウンロードジョブが見つかりません。",
        "error.start_download": "ダウンロードを開始できません。",
        "error.fetch_status": "ダウンロード状態を取得できません。",
        "error.download_failed": "ダウンロードに失敗しました。しばらくしてから再試行してください。",
        "error.output_missing": "ダウンロードは完了しましたが、出力ファイルが見つかりません。",
        "warning.no_ffmpeg": "ffmpeg が未インストールのため、直接取得できる mp4 形式を優先します。",
        "warning.no_node": "nodejs が未インストールのため、一部の YouTube 形式が不完全になる可能性があります。",
        "warning.no_cookies": "YouTube がサインイン確認を要求する場合は cookies ファイルをマウントしてください。",
    },
}


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.netloc not in YOUTUBE_HOSTS:
        return None

    if "youtu.be" in parsed.netloc:
        candidate = parsed.path.strip("/")
        return candidate or None

    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]

    shorts_match = re.match(r"^/shorts/([^/]+)", parsed.path)
    if shorts_match:
        return shorts_match.group(1)

    embed_match = re.match(r"^/embed/([^/]+)", parsed.path)
    if embed_match:
        return embed_match.group(1)

    return None


def build_watch_url(raw_url: str) -> str:
    video_id = extract_video_id(raw_url)
    if not video_id:
        raise ValueError("請輸入有效的 YouTube 影片網址。")
    return f"https://www.youtube.com/watch?v={video_id}"


def yt_dlp_exists() -> bool:
    return shutil.which("yt-dlp") is not None


def ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None


def normalize_quality(raw_quality: str) -> str:
    quality = raw_quality.strip().lower()
    if quality in QUALITY_OPTIONS:
        return quality
    return "best"


def build_download_command(url: str, quality: str) -> list[str]:
    output_template = str(DOWNLOADS_DIR / "%(title).120s.%(ext)s")
    selected_quality = QUALITY_OPTIONS[normalize_quality(quality)]
    base = [
        "yt-dlp",
        "--no-playlist",
        "--newline",
        "--restrict-filenames",
        "--js-runtimes",
        "node",
        "-o",
        output_template,
    ]

    if YTDLP_COOKIES_FILE and Path(YTDLP_COOKIES_FILE).is_file():
        base.extend(["--cookies", prepare_runtime_cookies_file()])

    if YTDLP_REMOTE_COMPONENTS:
        base.extend(["--remote-components", YTDLP_REMOTE_COMPONENTS])

    if ffmpeg_exists():
        return base + [
            "-f",
            selected_quality["ffmpeg_format"],
            "--merge-output-format",
            "mp4",
            url,
        ]

    return base + [
        "-f",
        selected_quality["direct_format"],
        url,
    ]


def create_job() -> tuple[str, dict[str, Any]]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "status": "queued",
        "progress": 0.0,
        "status_key": "progress.waiting",
        "status_text": "",
        "title": None,
        "filename": None,
        "warning": None,
        "warning_keys": [],
        "error": None,
        "error_key": None,
        "quality": "best",
    }
    with jobs_lock:
        download_jobs[job_id] = job
    return job_id, job


def update_job(job_id: str, **changes: Any) -> None:
    with jobs_lock:
        job = download_jobs.get(job_id)
        if not job:
            return
        job.update(changes)


def get_job(job_id: str) -> dict[str, Any] | None:
    with jobs_lock:
        job = download_jobs.get(job_id)
        if not job:
            return None
        return dict(job)


def find_latest_file(before: set[Path]) -> Path | None:
    candidates = [path for path in DOWNLOADS_DIR.iterdir() if path.is_file() and path not in before]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def parse_progress_line(line: str) -> tuple[float | None, str | None, str]:
    progress_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
    if progress_match:
        percent = float(progress_match.group(1))
        return percent, None, line

    if "Downloading webpage" in line or "Downloading initial data API JSON" in line:
        return 2.0, "progress.fetching_info", line
    if "Downloading player" in line or "Downloading m3u8 information" in line:
        return 5.0, "progress.analyzing_formats", line
    if "Downloading tv client config" in line or "Downloading ios player API JSON" in line:
        return 8.0, "progress.parsing_auth", line
    if "Merger" in line:
        return 96.0, "progress.merging_mp4", line
    if "has already been downloaded" in line:
        return 100.0, "progress.using_existing", line
    return None, None, line


def run_download_job(job_id: str, url: str, quality: str) -> None:
    try:
        normalized_url = build_watch_url(url)
        if not yt_dlp_exists():
            raise RuntimeError("yt-dlp is not installed.")

        before = set(DOWNLOADS_DIR.iterdir())
        command = build_download_command(normalized_url, quality)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE_DIR,
        )

        update_job(job_id, status="running", progress=1.0, status_key="progress.preparing", status_text="")
        output_lines: list[str] = []
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            output_lines.append(line)
            progress, status_key, status_text = parse_progress_line(line)
            if progress is not None:
                update_job(job_id, progress=min(progress, 99.0), status_key=status_key, status_text=status_text)
            else:
                update_job(job_id, status_key=status_key, status_text=status_text)

        completed = process.wait()

        if completed != 0:
            stderr = output_lines[-1] if output_lines else "下載失敗，請稍後再試。"
            update_job(job_id, status="error", progress=0.0, status_key="progress.failed", status_text="", error=stderr, error_key="error.download_failed")
            return

        downloaded_file = find_latest_file(before)
        if not downloaded_file:
            update_job(
                job_id,
                status="error",
                progress=0.0,
                status_key="progress.failed",
                status_text="",
                error="影片已完成，但找不到輸出檔案。",
                error_key="error.output_missing",
            )
            return

        update_job(
            job_id,
            status="completed",
            progress=100.0,
            status_key="progress.completed",
            status_text="",
            title=downloaded_file.stem,
            filename=downloaded_file.name,
            warning=build_runtime_warning(),
            warning_keys=build_runtime_warning_keys(),
            error=None,
            error_key=None,
            quality=normalize_quality(quality),
        )
    except Exception as exc:
        update_job(job_id, status="error", progress=0.0, status_key="progress.failed", status_text="", error=str(exc), error_key="error.download_failed")


def prepare_runtime_cookies_file() -> str:
    source = Path(YTDLP_COOKIES_FILE)
    runtime_dir = Path(tempfile.gettempdir()) / "youtube-to-mp4-cookies"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = runtime_dir / source.name
    shutil.copy2(source, runtime_file)
    return str(runtime_file)


def build_runtime_warning_keys() -> list[str]:
    warnings: list[str] = []
    if not ffmpeg_exists():
        warnings.append("warning.no_ffmpeg")
    if not shutil.which("node"):
        warnings.append("warning.no_node")
    if not (YTDLP_COOKIES_FILE and Path(YTDLP_COOKIES_FILE).is_file()):
        warnings.append("warning.no_cookies")
    return warnings


def build_runtime_warning() -> str | None:
    warnings = build_runtime_warning_keys()
    if not warnings:
        return None
    return " ".join(warnings)


@app.get("/")
def index():
    return render_template(
        "index.html",
        yt_dlp_ready=yt_dlp_exists(),
        ffmpeg_ready=ffmpeg_exists(),
        quality_options=QUALITY_OPTIONS,
        translations=TRANSLATIONS,
    )


@app.post("/api/download")
def download():
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    quality = normalize_quality(str(payload.get("quality", "best")))
    if not url:
        return jsonify({"error": "Please paste a YouTube video URL first.", "error_key": "error.empty_url"}), 400

    try:
        normalized_url = build_watch_url(url)
        job_id, _ = create_job()
        update_job(job_id, quality=quality)
        worker = threading.Thread(target=run_download_job, args=(job_id, normalized_url, quality), daemon=True)
        worker.start()
        return jsonify({"job_id": job_id})
    except ValueError as exc:
        return jsonify({"error": str(exc), "error_key": "error.invalid_url"}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc), "error_key": "error.start_download"}), 500


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Download job not found.", "error_key": "error.job_not_found"}), 404

    if job.get("filename"):
        job["download_url"] = f"/files/{job['filename']}"
    return jsonify(job)


@app.get("/files/<path:filename>")
def files(filename: str):
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
