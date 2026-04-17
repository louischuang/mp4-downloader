from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib import error as urllib_error
from urllib import request as urllib_request

from flask import Flask, jsonify, render_template, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", str(BASE_DIR / "downloads"))).resolve()
DOWNLOADS_DIR.mkdir(exist_ok=True)
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", str(BASE_DIR / "transcripts"))).resolve()
TRANSCRIPTS_DIR.mkdir(exist_ok=True)
VIDEO_INDEX_PATH = DOWNLOADS_DIR / ".video-index.json"
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "5000"))
APP_DEBUG = os.getenv("APP_DEBUG", "false").lower() == "true"
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", "").strip()
YTDLP_REMOTE_COMPONENTS = os.getenv("YTDLP_REMOTE_COMPONENTS", "ejs:github").strip()
STT_API_URL = os.getenv("STT_API_URL", "http://stt-service:8000").rstrip("/")
STT_DEFAULT_MODEL = os.getenv("STT_DEFAULT_MODEL", "small").strip() or "small"

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

app = Flask(__name__)
jobs_lock = threading.Lock()
video_index_lock = threading.Lock()
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
TRANSCRIPTION_MODELS = {
    "small": {"label_key": "stt.model.small"},
    "medium": {"label_key": "stt.model.medium"},
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
        "form.submit_transcribe": "下載與轉成文字",
        "form.quality": "下載畫質",
        "video.author": "作者：",
        "video.source": "影片網址",
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
        "modal.completed_title": "作業完成",
        "modal.completed_download": "已完成下載。",
        "modal.completed_download_transcribe": "已完成下載與轉文字。",
        "modal.close": "關閉",
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
        "stt.section_title": "影片轉文字",
        "stt.section_intro": "針對已下載的 MP4 產生文字稿與字幕檔，使用獨立的 faster-whisper STT 容器。",
        "stt.model_label": "轉錄模型",
        "stt.model.small": "small",
        "stt.model.medium": "medium",
        "stt.refresh": "重新整理影片清單",
        "stt.empty": "目前還沒有可供轉錄的 MP4 檔案。",
        "stt.transcribe": "轉文字",
        "stt.progress_title": "轉錄進度",
        "stt.queued": "等待轉錄開始",
        "stt.loading_model": "正在載入語音模型",
        "stt.loading_model_downloading": "正在下載與載入語音模型（已快取 {size}）",
        "stt.loading_model_cached": "正在載入語音模型（已快取 {size}）",
        "stt.transcribing": "正在進行語音轉文字",
        "stt.writing_files": "正在輸出轉錄檔案",
        "stt.completed": "轉錄完成",
        "stt.failed": "轉錄失敗",
        "stt.download_txt": "下載 TXT",
        "stt.download_srt": "下載 SRT",
        "stt.download_vtt": "下載 VTT",
        "stt.download_json": "下載 JSON",
        "stt.result_title": "轉錄完成：",
        "stt.result_files": "輸出檔案：",
        "stt.play": "播放",
        "stt.transcribed": "已轉文字",
        "stt.transcribed_action": "已轉文字",
        "stt.player_title": "影片播放與字幕驗證",
        "stt.player_close": "關閉",
        "stt.player_no_captions": "目前還沒有可用字幕，請先執行影片轉文字。",
        "stt.player_with_captions": "已掛載字幕，可直接在播放器中驗證。",
        "stt.error.fetch_videos": "無法取得影片清單。",
        "stt.error.start": "無法啟動轉錄工作。",
        "stt.error.status": "無法取得轉錄狀態。",
        "stt.error.service_unavailable": "STT 服務目前無法連線。",
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
        "form.submit_transcribe": "下载与转成文字",
        "form.quality": "下载画质",
        "video.author": "作者：",
        "video.source": "视频网址",
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
        "modal.completed_title": "任务完成",
        "modal.completed_download": "已完成下载。",
        "modal.completed_download_transcribe": "已完成下载与转文字。",
        "modal.close": "关闭",
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
        "stt.section_title": "视频转文字",
        "stt.section_intro": "针对已下载的 MP4 生成文字稿与字幕文件，使用独立的 faster-whisper STT 容器。",
        "stt.model_label": "转录模型",
        "stt.model.small": "small",
        "stt.model.medium": "medium",
        "stt.refresh": "刷新视频列表",
        "stt.empty": "目前还没有可供转录的 MP4 文件。",
        "stt.transcribe": "转文字",
        "stt.progress_title": "转录进度",
        "stt.queued": "等待转录开始",
        "stt.loading_model": "正在加载语音模型",
        "stt.loading_model_downloading": "正在下载并加载语音模型（已缓存 {size}）",
        "stt.loading_model_cached": "正在加载语音模型（已缓存 {size}）",
        "stt.transcribing": "正在进行语音转文字",
        "stt.writing_files": "正在输出转录文件",
        "stt.completed": "转录完成",
        "stt.failed": "转录失败",
        "stt.download_txt": "下载 TXT",
        "stt.download_srt": "下载 SRT",
        "stt.download_vtt": "下载 VTT",
        "stt.download_json": "下载 JSON",
        "stt.result_title": "转录完成：",
        "stt.result_files": "输出文件：",
        "stt.play": "播放",
        "stt.transcribed": "已转文字",
        "stt.transcribed_action": "已转文字",
        "stt.player_title": "视频播放与字幕验证",
        "stt.player_close": "关闭",
        "stt.player_no_captions": "目前还没有可用字幕，请先执行视频转文字。",
        "stt.player_with_captions": "已挂载字幕，可直接在播放器中验证。",
        "stt.error.fetch_videos": "无法取得视频列表。",
        "stt.error.start": "无法启动转录任务。",
        "stt.error.status": "无法取得转录状态。",
        "stt.error.service_unavailable": "STT 服务当前无法连接。",
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
        "form.submit_transcribe": "Download And Transcribe",
        "form.quality": "Quality",
        "video.author": "Author:",
        "video.source": "Source URL",
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
        "modal.completed_title": "Completed",
        "modal.completed_download": "Download completed.",
        "modal.completed_download_transcribe": "Download and transcription completed.",
        "modal.close": "Close",
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
        "stt.section_title": "Video To Text",
        "stt.section_intro": "Generate transcripts and subtitle files from downloaded MP4 videos using a separate faster-whisper STT container.",
        "stt.model_label": "Transcription Model",
        "stt.model.small": "small",
        "stt.model.medium": "medium",
        "stt.refresh": "Refresh Video List",
        "stt.empty": "There are no MP4 files available for transcription yet.",
        "stt.transcribe": "Transcribe",
        "stt.progress_title": "Transcription Progress",
        "stt.queued": "Waiting to start transcription",
        "stt.loading_model": "Loading speech model",
        "stt.loading_model_downloading": "Downloading and loading speech model ({size} cached)",
        "stt.loading_model_cached": "Loading speech model ({size} cached)",
        "stt.transcribing": "Running speech-to-text",
        "stt.writing_files": "Writing transcript files",
        "stt.completed": "Transcription completed",
        "stt.failed": "Transcription failed",
        "stt.download_txt": "Download TXT",
        "stt.download_srt": "Download SRT",
        "stt.download_vtt": "Download VTT",
        "stt.download_json": "Download JSON",
        "stt.result_title": "Transcription completed:",
        "stt.result_files": "Output files:",
        "stt.play": "Play",
        "stt.transcribed": "Transcribed",
        "stt.transcribed_action": "Transcribed",
        "stt.player_title": "Video Playback And Caption Review",
        "stt.player_close": "Close",
        "stt.player_no_captions": "No captions are available yet. Run transcription first.",
        "stt.player_with_captions": "Captions are attached and ready for review.",
        "stt.error.fetch_videos": "Unable to fetch the video list.",
        "stt.error.start": "Unable to start the transcription job.",
        "stt.error.status": "Unable to fetch the transcription status.",
        "stt.error.service_unavailable": "The STT service is currently unavailable.",
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
        "form.submit_transcribe": "ダウンロードして文字起こし",
        "form.quality": "画質",
        "video.author": "作者：",
        "video.source": "動画URL",
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
        "modal.completed_title": "完了",
        "modal.completed_download": "ダウンロードが完了しました。",
        "modal.completed_download_transcribe": "ダウンロードと文字起こしが完了しました。",
        "modal.close": "閉じる",
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
        "stt.section_title": "動画文字起こし",
        "stt.section_intro": "ダウンロード済み MP4 から文字起こしと字幕ファイルを生成します。独立した faster-whisper STT コンテナを使用します。",
        "stt.model_label": "文字起こしモデル",
        "stt.model.small": "small",
        "stt.model.medium": "medium",
        "stt.refresh": "動画一覧を更新",
        "stt.empty": "文字起こし可能な MP4 ファイルはまだありません。",
        "stt.transcribe": "文字起こし",
        "stt.progress_title": "文字起こし進捗",
        "stt.queued": "文字起こし開始待ち",
        "stt.loading_model": "音声モデルを読み込み中",
        "stt.loading_model_downloading": "音声モデルをダウンロードして読み込み中（{size} をキャッシュ済み）",
        "stt.loading_model_cached": "音声モデルを読み込み中（{size} をキャッシュ済み）",
        "stt.transcribing": "音声文字起こし中",
        "stt.writing_files": "文字起こしファイルを書き出し中",
        "stt.completed": "文字起こし完了",
        "stt.failed": "文字起こし失敗",
        "stt.download_txt": "TXT をダウンロード",
        "stt.download_srt": "SRT をダウンロード",
        "stt.download_vtt": "VTT をダウンロード",
        "stt.download_json": "JSON をダウンロード",
        "stt.result_title": "文字起こし完了：",
        "stt.result_files": "出力ファイル：",
        "stt.play": "再生",
        "stt.transcribed": "文字起こし済み",
        "stt.transcribed_action": "文字起こし済み",
        "stt.player_title": "動画再生と字幕確認",
        "stt.player_close": "閉じる",
        "stt.player_no_captions": "利用可能な字幕はまだありません。先に文字起こしを実行してください。",
        "stt.player_with_captions": "字幕を読み込み済みです。プレイヤー上で確認できます。",
        "stt.error.fetch_videos": "動画一覧を取得できません。",
        "stt.error.start": "文字起こしジョブを開始できません。",
        "stt.error.status": "文字起こし状態を取得できません。",
        "stt.error.service_unavailable": "STT サービスに接続できません。",
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


def build_ytdlp_base_command() -> list[str]:
    base = [
        "yt-dlp",
        "--no-playlist",
        "--newline",
        "--restrict-filenames",
        "--js-runtimes",
        "node",
    ]

    if YTDLP_COOKIES_FILE and Path(YTDLP_COOKIES_FILE).is_file():
        base.extend(["--cookies", prepare_runtime_cookies_file()])

    if YTDLP_REMOTE_COMPONENTS:
        base.extend(["--remote-components", YTDLP_REMOTE_COMPONENTS])

    return base


def build_download_command(url: str, quality: str) -> list[str]:
    output_template = str(DOWNLOADS_DIR / "%(title).120s.%(ext)s")
    selected_quality = QUALITY_OPTIONS[normalize_quality(quality)]
    base = build_ytdlp_base_command() + [
        "-o",
        output_template,
    ]

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


def fetch_video_metadata(url: str) -> dict[str, Any] | None:
    command = build_ytdlp_base_command() + [
        "--dump-single-json",
        "--skip-download",
        url,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True, cwd=BASE_DIR)
    except subprocess.CalledProcessError:
        return None

    stdout = completed.stdout.strip()
    if not stdout:
        return None

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None

    return {
        "video_id": payload.get("id"),
        "title": payload.get("title"),
        "uploader": payload.get("uploader") or payload.get("channel"),
        "webpage_url": payload.get("webpage_url") or url,
    }


def load_video_index() -> dict[str, dict[str, Any]]:
    with video_index_lock:
        if not VIDEO_INDEX_PATH.is_file():
            return {}
        try:
            payload = json.loads(VIDEO_INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def save_video_index(index: dict[str, dict[str, Any]]) -> None:
    with video_index_lock:
        VIDEO_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_video_index_entry(filename: str, metadata: dict[str, Any]) -> None:
    index = load_video_index()
    existing = index.get(filename, {})
    merged = {
        **existing,
        **metadata,
        "filename": filename,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    index[filename] = merged
    save_video_index(index)


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


def list_video_files() -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    index = load_video_index()
    for path in sorted(DOWNLOADS_DIR.glob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True):
        vtt_path = TRANSCRIPTS_DIR / f"{path.stem}.vtt"
        txt_path = TRANSCRIPTS_DIR / f"{path.stem}.txt"
        entry = index.get(path.name, {})
        videos.append(
            {
                "filename": path.name,
                "title": entry.get("title") or path.stem,
                "uploader": entry.get("uploader"),
                "youtube_url": entry.get("webpage_url"),
                "size_bytes": path.stat().st_size,
                "media_url": f"/media/{path.name}",
                "download_url": f"/files/{path.name}",
                "captions_url": f"/transcripts/{vtt_path.name}" if vtt_path.is_file() else None,
                "is_transcribed": vtt_path.is_file() or txt_path.is_file(),
            }
        )
    return videos


def stt_request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib_request.Request(f"{STT_API_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {"error": str(exc)}
    except (urllib_error.URLError, TimeoutError):
        return 503, {"error": "STT service unavailable", "error_key": "stt.error.service_unavailable"}


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

        metadata = fetch_video_metadata(normalized_url) or {}
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
            title=metadata.get("title") or downloaded_file.stem,
            filename=downloaded_file.name,
            warning=build_runtime_warning(),
            warning_keys=build_runtime_warning_keys(),
            error=None,
            error_key=None,
            quality=normalize_quality(quality),
        )
        upsert_video_index_entry(
            downloaded_file.name,
            {
                "title": metadata.get("title") or downloaded_file.stem,
                "uploader": metadata.get("uploader"),
                "webpage_url": metadata.get("webpage_url") or normalized_url,
                "video_id": metadata.get("video_id"),
            },
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
        transcription_models=TRANSCRIPTION_MODELS,
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


@app.get("/api/videos")
def videos():
    return jsonify({"videos": list_video_files()})


@app.post("/api/transcriptions")
def create_transcription():
    payload = request.get_json(silent=True) or {}
    filename = str(payload.get("filename", "")).strip()
    model = str(payload.get("model", STT_DEFAULT_MODEL)).strip() or STT_DEFAULT_MODEL

    if not filename:
        return jsonify({"error": "filename is required", "error_key": "stt.error.start"}), 400

    if not (DOWNLOADS_DIR / filename).is_file():
        return jsonify({"error": "Source MP4 file not found.", "error_key": "stt.error.start"}), 404

    status_code, data = stt_request("/jobs", method="POST", payload={"filename": filename, "model": model})
    return jsonify(data), status_code


@app.get("/api/transcriptions/<job_id>")
def transcription_status(job_id: str):
    status_code, data = stt_request(f"/jobs/{job_id}")
    output_files = data.get("output_files", {})
    if output_files:
        data["download_urls"] = {
            key: f"/transcripts/{value}"
            for key, value in output_files.items()
        }
    return jsonify(data), status_code


@app.get("/files/<path:filename>")
def files(filename: str):
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)


@app.get("/media/<path:filename>")
def media(filename: str):
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=False)


@app.get("/transcripts/<path:filename>")
def transcripts(filename: str):
    return send_from_directory(TRANSCRIPTS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
