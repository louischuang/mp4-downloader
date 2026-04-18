from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import threading
import uuid
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib import error as urllib_error
from urllib import request as urllib_request

from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image, ImageDraw, ImageFont
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
PACKAGE_JSON_PATH = BASE_DIR / "package.json"
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


def load_app_version() -> str:
    if not PACKAGE_JSON_PATH.is_file():
        return "1.0.0"
    try:
        payload = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "1.0.0"
    version = str(payload.get("version", "")).strip()
    return version or "1.0.0"


API_VERSION = load_app_version()
BURN_BASE_FONT_SIZE = 50.0
BURN_FONT_SIZE_OPTIONS = {
    "minus_20": 0.8,
    "minus_10": 0.9,
    "zero": 1.0,
    "plus_10": 1.1,
    "plus_20": 1.2,
    "plus_30": 1.3,
}
BURN_FONT_FAMILIES = {
    "sans": "Noto Sans CJK TC",
    "serif": "Noto Serif CJK TC",
    "mono": "Noto Sans Mono CJK TC",
}
BURN_DEFAULT_SETTINGS = {
    "size": "zero",
    "font_family": "sans",
    "text_color": "#ffffff",
    "outline_color": "#000000",
    "outline_width": 0.8,
    "position": "bottom",
    "line_spacing": 0,
    "margin_v": 34,
    "margin_l": 42,
    "margin_r": 42,
    "shadow": False,
    "background": False,
    "background_color": "#000000",
    "background_opacity": 56,
    "background_size": 32,
    "background_radius": 22,
    "max_chars_per_line": 18,
}
BURN_POSITION_OPTIONS = {
    "bottom": 2,
    "middle": 5,
    "top": 8,
}
BURN_BACKGROUND_HORIZONTAL_PADDING_FACTOR = 0.25
BURN_BACKGROUND_VERTICAL_PADDING_FACTOR = 0.44
BURN_BACKGROUND_MIN_VERTICAL_PADDING = 10
BURN_BACKGROUND_WIDTH_SCALE = 0.85

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
        "form.tab_youtube": "YouTube 下載",
        "form.tab_upload": "上傳 MP4",
        "form.submit": "開始下載",
        "form.submit_transcribe": "下載與轉成文字",
        "form.quality": "下載畫質",
        "upload.title": "影片標題",
        "upload.title_placeholder": "請輸入這支影片的標題",
        "upload.file": "本機 MP4 檔案",
        "upload.submit": "上傳並轉成文字",
        "upload.hint": "上傳完成後，系統會自動開始進行轉文字。",
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
        "download.modal_title": "下載檔案",
        "download.modal_close": "取消",
        "download.video": "下載影片",
        "download.transcript": "下載文字檔",
        "download.none": "目前沒有可下載的文字檔。",
        "download.in_progress": "準備下載中...",
        "download.option_video": "MP4 影片",
        "download.option_txt": "TXT 逐字稿",
        "download.option_srt": "SRT 字幕",
        "download.option_vtt": "VTT 字幕",
        "download.option_json": "JSON 結構資料",
        "action.play": "播放影片",
        "action.source": "打開影片網址",
        "action.download": "下載",
        "action.edit_subtitles": "編輯字幕",
        "action.transcribe": "轉文字",
        "action.transcribed": "已轉換",
        "action.retranscribe": "重新轉文字",
        "action.burn_subtitles": "產生燒錄 MP4",
        "action.delete": "刪除影片",
        "retranscribe.title": "重新轉文字",
        "retranscribe.message": "要重新為「{title}」執行一次文字轉換嗎？",
        "retranscribe.confirm": "重新轉換",
        "retranscribe.cancel": "取消",
        "delete_video.title": "刪除影片",
        "delete_video.message": "確定要刪除「{title}」嗎？這會一起刪除影片、字幕與逐字稿檔案。",
        "delete_video.confirm": "確認刪除",
        "delete_video.cancel": "取消",
        "modal.completed_title": "作業完成",
        "modal.completed_download": "已完成下載。",
        "modal.completed_download_transcribe": "已完成下載與轉文字。",
        "modal.completed_burned_video": "已完成燒錄字幕 MP4。",
        "modal.completed_subtitle_save": "字幕已儲存。",
        "modal.completed_delete_video": "已經刪除完成。",
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
        "upload.error.file_required": "請先選擇一個 MP4 檔案。",
        "upload.error.title_required": "請先輸入影片標題。",
        "upload.error.invalid_type": "目前只支援上傳 MP4 檔案。",
        "upload.error.save_failed": "無法儲存上傳的 MP4 檔案。",
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
        "stt.player_burned_video": "這支影片已經是燒錄字幕版，播放器不會再額外疊加字幕軌。",
        "stt.error.fetch_videos": "無法取得影片清單。",
        "stt.error.start": "無法啟動轉錄工作。",
        "stt.error.status": "無法取得轉錄狀態。",
        "stt.error.service_unavailable": "STT 服務目前無法連線。",
        "burn.progress_title": "字幕燒錄進度",
        "burn.preparing": "正在準備字幕燒錄",
        "burn.rendering": "正在產生燒錄字幕 MP4",
        "burn.completed": "燒錄字幕 MP4 已完成",
        "burn.failed": "燒錄字幕 MP4 失敗",
        "burn.error.start": "無法啟動燒錄字幕 MP4。",
        "burn.error.source_missing": "找不到原始 MP4 檔案。",
        "burn.error.subtitle_missing": "找不到可燒錄的 SRT 字幕檔。",
        "burn.error.ffmpeg_missing": "系統尚未安裝 ffmpeg，無法產生燒錄字幕 MP4。",
        "burn.error.output_missing": "燒錄完成，但找不到新的 MP4 檔案。",
        "burn.settings_title": "燒錄字幕 MP4 設定",
        "burn.settings_intro": "為「{title}」選擇字幕大小、配色與效果，再開始產生新的字幕 MP4。",
        "burn.settings_size": "字幕大小",
        "burn.settings_size_minus_20": "-20%",
        "burn.settings_size_minus_10": "-10%",
        "burn.settings_size_zero": "0%",
        "burn.settings_size_plus_10": "+10%",
        "burn.settings_size_plus_20": "+20%",
        "burn.settings_size_plus_30": "+30%",
        "burn.settings_font_family": "字型家族",
        "burn.settings_font_family_sans": "黑體",
        "burn.settings_font_family_serif": "明體",
        "burn.settings_font_family_mono": "等寬字體",
        "burn.settings_text_color": "字體顏色",
        "burn.settings_outline_color": "外框顏色",
        "burn.settings_outline_width": "外框寬度",
        "burn.settings_position": "字幕位置",
        "burn.settings_position_bottom": "底部",
        "burn.settings_position_middle": "中間",
        "burn.settings_position_top": "頂部",
        "burn.settings_line_spacing": "行距",
        "burn.settings_margin_v": "上下邊距",
        "burn.settings_margin_l": "左側安全邊距",
        "burn.settings_margin_r": "右側安全邊距",
        "burn.settings_background_color": "背景顏色",
        "burn.settings_background_opacity": "背景透明度",
        "burn.settings_background_size": "背景大小",
        "burn.settings_background_radius": "圓角大小",
        "burn.settings_max_chars": "每行最大字數",
        "burn.settings_profile": "樣式 Profile",
        "burn.settings_profile_custom": "目前樣式",
        "burn.settings_profile_name": "Profile 名稱",
        "burn.settings_profile_name_placeholder": "例如：會議字幕",
        "burn.settings_profile_save": "儲存 Profile",
        "burn.settings_profile_delete": "刪除 Profile",
        "burn.settings_preview": "即時預覽",
        "burn.settings_preview_line_1": "這是一段字幕預覽",
        "burn.settings_preview_line_2": "你可以在這裡先確認樣式",
        "burn.settings_effects": "字幕效果",
        "burn.settings_shadow": "加上陰影",
        "burn.settings_background": "增加透明背景",
        "burn.settings_submit": "開始燒錄",
        "burn.settings_cancel": "取消",
        "burn.settings_hint": "建議之後可再加入字幕位置、上下邊距、字型家族與每行字數限制。",
        "subtitle.editor_title": "編輯 SRT 字幕",
        "subtitle.editor_intro": "修改這支影片的 SRT 字幕內容，儲存後再重新產生燒錄 MP4。",
        "subtitle.editor_save": "儲存字幕",
        "subtitle.editor_cancel": "取消",
        "subtitle.editor_placeholder": "請在這裡編輯 SRT 內容",
        "subtitle.error.fetch": "無法讀取字幕內容。",
        "subtitle.error.save": "無法儲存字幕內容。",
        "subtitle.error.missing": "找不到這支影片的 SRT 字幕檔。",
        "delete_video.error.not_found": "找不到要刪除的影片檔案。",
        "delete_video.error.failed": "刪除影片失敗，請稍後再試。",
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
        "form.tab_youtube": "YouTube 下载",
        "form.tab_upload": "上传 MP4",
        "form.submit": "开始下载",
        "form.submit_transcribe": "下载与转成文字",
        "form.quality": "下载画质",
        "upload.title": "视频标题",
        "upload.title_placeholder": "请输入这支视频的标题",
        "upload.file": "本地 MP4 文件",
        "upload.submit": "上传并转成文字",
        "upload.hint": "上传完成后，系统会自动开始进行转文字。",
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
        "download.modal_title": "下载文件",
        "download.modal_close": "取消",
        "download.video": "下载视频",
        "download.transcript": "下载文字文件",
        "download.none": "目前没有可下载的文字文件。",
        "download.in_progress": "准备下载中...",
        "download.option_video": "MP4 视频",
        "download.option_txt": "TXT 逐字稿",
        "download.option_srt": "SRT 字幕",
        "download.option_vtt": "VTT 字幕",
        "download.option_json": "JSON 结构资料",
        "action.play": "播放视频",
        "action.source": "打开视频网址",
        "action.download": "下载",
        "action.edit_subtitles": "编辑字幕",
        "action.transcribe": "转文字",
        "action.transcribed": "已转换",
        "action.retranscribe": "重新转文字",
        "action.burn_subtitles": "生成烧录 MP4",
        "action.delete": "删除视频",
        "retranscribe.title": "重新转文字",
        "retranscribe.message": "要重新为“{title}”执行一次文字转换吗？",
        "retranscribe.confirm": "重新转换",
        "retranscribe.cancel": "取消",
        "delete_video.title": "删除视频",
        "delete_video.message": "确定要删除“{title}”吗？这会一起删除视频、字幕和逐字稿文件。",
        "delete_video.confirm": "确认删除",
        "delete_video.cancel": "取消",
        "modal.completed_title": "任务完成",
        "modal.completed_download": "已完成下载。",
        "modal.completed_download_transcribe": "已完成下载与转文字。",
        "modal.completed_burned_video": "已完成烧录字幕 MP4。",
        "modal.completed_subtitle_save": "字幕已保存。",
        "modal.completed_delete_video": "已经删除完成。",
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
        "upload.error.file_required": "请先选择一个 MP4 文件。",
        "upload.error.title_required": "请先输入视频标题。",
        "upload.error.invalid_type": "目前只支持上传 MP4 文件。",
        "upload.error.save_failed": "无法保存上传的 MP4 文件。",
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
        "stt.player_burned_video": "这支视频已经是烧录字幕版，播放器不会再额外叠加字幕轨。",
        "stt.error.fetch_videos": "无法取得视频列表。",
        "stt.error.start": "无法启动转录任务。",
        "stt.error.status": "无法取得转录状态。",
        "stt.error.service_unavailable": "STT 服务当前无法连接。",
        "burn.progress_title": "字幕烧录进度",
        "burn.preparing": "正在准备字幕烧录",
        "burn.rendering": "正在生成烧录字幕 MP4",
        "burn.completed": "烧录字幕 MP4 已完成",
        "burn.failed": "烧录字幕 MP4 失败",
        "burn.error.start": "无法启动烧录字幕 MP4。",
        "burn.error.source_missing": "找不到原始 MP4 文件。",
        "burn.error.subtitle_missing": "找不到可烧录的 SRT 字幕文件。",
        "burn.error.ffmpeg_missing": "系统尚未安装 ffmpeg，无法生成烧录字幕 MP4。",
        "burn.error.output_missing": "烧录完成，但找不到新的 MP4 文件。",
        "burn.settings_title": "烧录字幕 MP4 设置",
        "burn.settings_intro": "为“{title}”选择字幕大小、配色与效果，然后开始生成新的字幕 MP4。",
        "burn.settings_size": "字幕大小",
        "burn.settings_size_minus_20": "-20%",
        "burn.settings_size_minus_10": "-10%",
        "burn.settings_size_zero": "0%",
        "burn.settings_size_plus_10": "+10%",
        "burn.settings_size_plus_20": "+20%",
        "burn.settings_size_plus_30": "+30%",
        "burn.settings_font_family": "字体家族",
        "burn.settings_font_family_sans": "黑体",
        "burn.settings_font_family_serif": "明体",
        "burn.settings_font_family_mono": "等宽字体",
        "burn.settings_text_color": "字体颜色",
        "burn.settings_outline_color": "描边颜色",
        "burn.settings_outline_width": "描边宽度",
        "burn.settings_position": "字幕位置",
        "burn.settings_position_bottom": "底部",
        "burn.settings_position_middle": "中间",
        "burn.settings_position_top": "顶部",
        "burn.settings_line_spacing": "行距",
        "burn.settings_margin_v": "上下边距",
        "burn.settings_margin_l": "左侧安全边距",
        "burn.settings_margin_r": "右侧安全边距",
        "burn.settings_background_color": "背景颜色",
        "burn.settings_background_opacity": "背景透明度",
        "burn.settings_background_size": "背景大小",
        "burn.settings_background_radius": "圆角大小",
        "burn.settings_max_chars": "每行最大字数",
        "burn.settings_profile": "样式 Profile",
        "burn.settings_profile_custom": "当前样式",
        "burn.settings_profile_name": "Profile 名称",
        "burn.settings_profile_name_placeholder": "例如：会议字幕",
        "burn.settings_profile_save": "保存 Profile",
        "burn.settings_profile_delete": "删除 Profile",
        "burn.settings_preview": "即时预览",
        "burn.settings_preview_line_1": "这是一段字幕预览",
        "burn.settings_preview_line_2": "你可以先在这里确认样式",
        "burn.settings_effects": "字幕效果",
        "burn.settings_shadow": "加上阴影",
        "burn.settings_background": "增加透明背景",
        "burn.settings_submit": "开始烧录",
        "burn.settings_cancel": "取消",
        "burn.settings_hint": "建议之后再加入字幕位置、上下边距、字体家族与每行字数限制。",
        "subtitle.editor_title": "编辑 SRT 字幕",
        "subtitle.editor_intro": "修改这支视频的 SRT 字幕内容，保存后再重新生成烧录 MP4。",
        "subtitle.editor_save": "保存字幕",
        "subtitle.editor_cancel": "取消",
        "subtitle.editor_placeholder": "请在这里编辑 SRT 内容",
        "subtitle.error.fetch": "无法读取字幕内容。",
        "subtitle.error.save": "无法保存字幕内容。",
        "subtitle.error.missing": "找不到这支视频的 SRT 字幕文件。",
        "delete_video.error.not_found": "找不到要删除的视频文件。",
        "delete_video.error.failed": "删除视频失败，请稍后再试。",
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
        "form.tab_youtube": "YouTube Download",
        "form.tab_upload": "Upload MP4",
        "form.submit": "Download",
        "form.submit_transcribe": "Download And Transcribe",
        "form.quality": "Quality",
        "upload.title": "Video Title",
        "upload.title_placeholder": "Enter a title for this video",
        "upload.file": "Local MP4 File",
        "upload.submit": "Upload And Transcribe",
        "upload.hint": "The service starts transcription automatically after the upload finishes.",
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
        "download.modal_title": "Download Files",
        "download.modal_close": "Cancel",
        "download.video": "Download Video",
        "download.transcript": "Download Transcript Files",
        "download.none": "No transcript files are available yet.",
        "download.in_progress": "Preparing download...",
        "download.option_video": "MP4 Video",
        "download.option_txt": "TXT Transcript",
        "download.option_srt": "SRT Captions",
        "download.option_vtt": "VTT Captions",
        "download.option_json": "JSON Data",
        "action.play": "Play video",
        "action.source": "Open source URL",
        "action.download": "Download",
        "action.edit_subtitles": "Edit Subtitles",
        "action.transcribe": "Transcribe",
        "action.transcribed": "Converted",
        "action.retranscribe": "Retranscribe",
        "action.burn_subtitles": "Create Burned MP4",
        "action.delete": "Delete Video",
        "retranscribe.title": "Run Transcription Again",
        "retranscribe.message": "Do you want to transcribe \"{title}\" again?",
        "retranscribe.confirm": "Transcribe Again",
        "retranscribe.cancel": "Cancel",
        "delete_video.title": "Delete Video",
        "delete_video.message": "Delete \"{title}\"? This will also remove the video, subtitle, and transcript files.",
        "delete_video.confirm": "Delete",
        "delete_video.cancel": "Cancel",
        "modal.completed_title": "Completed",
        "modal.completed_download": "Download completed.",
        "modal.completed_download_transcribe": "Download and transcription completed.",
        "modal.completed_burned_video": "Subtitle-burned MP4 completed.",
        "modal.completed_subtitle_save": "Subtitle file saved.",
        "modal.completed_delete_video": "Deletion completed.",
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
        "upload.error.file_required": "Please choose an MP4 file first.",
        "upload.error.title_required": "Please enter a video title first.",
        "upload.error.invalid_type": "Only MP4 uploads are supported.",
        "upload.error.save_failed": "Unable to save the uploaded MP4 file.",
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
        "stt.player_burned_video": "This video already has burned-in subtitles, so the player will not overlay a separate caption track.",
        "stt.error.fetch_videos": "Unable to fetch the video list.",
        "stt.error.start": "Unable to start the transcription job.",
        "stt.error.status": "Unable to fetch the transcription status.",
        "stt.error.service_unavailable": "The STT service is currently unavailable.",
        "burn.progress_title": "Subtitle Burn Progress",
        "burn.preparing": "Preparing subtitle burn job",
        "burn.rendering": "Rendering subtitle-burned MP4",
        "burn.completed": "Subtitle-burned MP4 completed",
        "burn.failed": "Subtitle-burned MP4 failed",
        "burn.error.start": "Unable to start the subtitle-burned MP4 job.",
        "burn.error.source_missing": "Source MP4 file not found.",
        "burn.error.subtitle_missing": "SRT subtitle file not found.",
        "burn.error.ffmpeg_missing": "ffmpeg is required to create a subtitle-burned MP4.",
        "burn.error.output_missing": "The burned MP4 finished, but the new output file could not be found.",
        "burn.settings_title": "Burned MP4 Settings",
        "burn.settings_intro": "Choose subtitle size, color, and effects for \"{title}\" before rendering a new burned MP4.",
        "burn.settings_size": "Subtitle Size",
        "burn.settings_size_minus_20": "-20%",
        "burn.settings_size_minus_10": "-10%",
        "burn.settings_size_zero": "0%",
        "burn.settings_size_plus_10": "+10%",
        "burn.settings_size_plus_20": "+20%",
        "burn.settings_size_plus_30": "+30%",
        "burn.settings_font_family": "Font Family",
        "burn.settings_font_family_sans": "Sans",
        "burn.settings_font_family_serif": "Serif",
        "burn.settings_font_family_mono": "Monospace",
        "burn.settings_text_color": "Text Color",
        "burn.settings_outline_color": "Outline Color",
        "burn.settings_outline_width": "Outline Width",
        "burn.settings_position": "Subtitle Position",
        "burn.settings_position_bottom": "Bottom",
        "burn.settings_position_middle": "Middle",
        "burn.settings_position_top": "Top",
        "burn.settings_line_spacing": "Line Spacing",
        "burn.settings_margin_v": "Vertical Margin",
        "burn.settings_margin_l": "Left Safe Margin",
        "burn.settings_margin_r": "Right Safe Margin",
        "burn.settings_background_color": "Background Color",
        "burn.settings_background_opacity": "Background Opacity",
        "burn.settings_background_size": "Background Size",
        "burn.settings_background_radius": "Corner Radius",
        "burn.settings_max_chars": "Max Chars Per Line",
        "burn.settings_profile": "Style Profile",
        "burn.settings_profile_custom": "Current Style",
        "burn.settings_profile_name": "Profile Name",
        "burn.settings_profile_name_placeholder": "e.g. Meeting captions",
        "burn.settings_profile_save": "Save Profile",
        "burn.settings_profile_delete": "Delete Profile",
        "burn.settings_preview": "Live Preview",
        "burn.settings_preview_line_1": "This is a subtitle preview",
        "burn.settings_preview_line_2": "Use it to confirm the style first",
        "burn.settings_effects": "Effects",
        "burn.settings_shadow": "Add shadow",
        "burn.settings_background": "Add translucent background",
        "burn.settings_submit": "Start Burn",
        "burn.settings_cancel": "Cancel",
        "burn.settings_hint": "Good future options to add are subtitle position, vertical margin, font family, and max characters per line.",
        "subtitle.editor_title": "Edit SRT Subtitles",
        "subtitle.editor_intro": "Update the SRT subtitle content for this video, then create a new burned MP4 when you are ready.",
        "subtitle.editor_save": "Save Subtitles",
        "subtitle.editor_cancel": "Cancel",
        "subtitle.editor_placeholder": "Edit the SRT content here",
        "subtitle.error.fetch": "Unable to load subtitle content.",
        "subtitle.error.save": "Unable to save subtitle content.",
        "subtitle.error.missing": "The SRT subtitle file could not be found for this video.",
        "delete_video.error.not_found": "The video file to delete could not be found.",
        "delete_video.error.failed": "Failed to delete the video. Please try again later.",
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
        "form.tab_youtube": "YouTube ダウンロード",
        "form.tab_upload": "MP4 をアップロード",
        "form.submit": "ダウンロード開始",
        "form.submit_transcribe": "ダウンロードして文字起こし",
        "form.quality": "画質",
        "upload.title": "動画タイトル",
        "upload.title_placeholder": "この動画のタイトルを入力してください",
        "upload.file": "ローカル MP4 ファイル",
        "upload.submit": "アップロードして文字起こし",
        "upload.hint": "アップロード完了後、自動で文字起こしが始まります。",
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
        "download.modal_title": "ファイルをダウンロード",
        "download.modal_close": "キャンセル",
        "download.video": "動画をダウンロード",
        "download.transcript": "文字起こしファイルをダウンロード",
        "download.none": "ダウンロード可能な文字起こしファイルはまだありません。",
        "download.in_progress": "ダウンロード準備中...",
        "download.option_video": "MP4 動画",
        "download.option_txt": "TXT 文字起こし",
        "download.option_srt": "SRT 字幕",
        "download.option_vtt": "VTT 字幕",
        "download.option_json": "JSON データ",
        "action.play": "動画を再生",
        "action.source": "動画URLを開く",
        "action.download": "ダウンロード",
        "action.edit_subtitles": "字幕を編集",
        "action.transcribe": "文字起こし",
        "action.transcribed": "変換済み",
        "action.retranscribe": "再文字起こし",
        "action.burn_subtitles": "字幕焼き込み MP4 を生成",
        "action.delete": "動画を削除",
        "retranscribe.title": "文字起こしを再実行",
        "retranscribe.message": "「{title}」の文字起こしをもう一度実行しますか？",
        "retranscribe.confirm": "再変換",
        "retranscribe.cancel": "キャンセル",
        "delete_video.title": "動画を削除",
        "delete_video.message": "「{title}」を削除しますか？動画、字幕、文字起こしファイルも一緒に削除されます。",
        "delete_video.confirm": "削除する",
        "delete_video.cancel": "キャンセル",
        "modal.completed_title": "完了",
        "modal.completed_download": "ダウンロードが完了しました。",
        "modal.completed_download_transcribe": "ダウンロードと文字起こしが完了しました。",
        "modal.completed_burned_video": "字幕焼き込み MP4 の生成が完了しました。",
        "modal.completed_subtitle_save": "字幕を保存しました。",
        "modal.completed_delete_video": "削除が完了しました。",
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
        "upload.error.file_required": "先に MP4 ファイルを選択してください。",
        "upload.error.title_required": "先に動画タイトルを入力してください。",
        "upload.error.invalid_type": "アップロードできるのは MP4 ファイルのみです。",
        "upload.error.save_failed": "アップロードした MP4 ファイルを保存できませんでした。",
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
        "stt.player_burned_video": "この動画は字幕焼き込み版のため、プレイヤーでは別の字幕トラックを重ねません。",
        "stt.error.fetch_videos": "動画一覧を取得できません。",
        "stt.error.start": "文字起こしジョブを開始できません。",
        "stt.error.status": "文字起こし状態を取得できません。",
        "stt.error.service_unavailable": "STT サービスに接続できません。",
        "burn.progress_title": "字幕焼き込み進捗",
        "burn.preparing": "字幕焼き込みジョブを準備中",
        "burn.rendering": "字幕焼き込み MP4 を生成中",
        "burn.completed": "字幕焼き込み MP4 の生成が完了しました",
        "burn.failed": "字幕焼き込み MP4 の生成に失敗しました",
        "burn.error.start": "字幕焼き込み MP4 ジョブを開始できません。",
        "burn.error.source_missing": "元の MP4 ファイルが見つかりません。",
        "burn.error.subtitle_missing": "焼き込み可能な SRT 字幕ファイルが見つかりません。",
        "burn.error.ffmpeg_missing": "字幕焼き込み MP4 を生成するには ffmpeg が必要です。",
        "burn.error.output_missing": "処理は完了しましたが、新しい MP4 ファイルが見つかりません。",
        "burn.settings_title": "字幕焼き込み MP4 設定",
        "burn.settings_intro": "「{title}」の字幕サイズ、配色、効果を選んでから新しい字幕焼き込み MP4 を生成します。",
        "burn.settings_size": "字幕サイズ",
        "burn.settings_size_minus_20": "-20%",
        "burn.settings_size_minus_10": "-10%",
        "burn.settings_size_zero": "0%",
        "burn.settings_size_plus_10": "+10%",
        "burn.settings_size_plus_20": "+20%",
        "burn.settings_size_plus_30": "+30%",
        "burn.settings_font_family": "フォント",
        "burn.settings_font_family_sans": "ゴシック",
        "burn.settings_font_family_serif": "明朝",
        "burn.settings_font_family_mono": "等幅",
        "burn.settings_text_color": "文字色",
        "burn.settings_outline_color": "縁取り色",
        "burn.settings_outline_width": "縁取り幅",
        "burn.settings_position": "字幕位置",
        "burn.settings_position_bottom": "下",
        "burn.settings_position_middle": "中央",
        "burn.settings_position_top": "上",
        "burn.settings_line_spacing": "行間",
        "burn.settings_margin_v": "上下マージン",
        "burn.settings_margin_l": "左の安全マージン",
        "burn.settings_margin_r": "右の安全マージン",
        "burn.settings_background_color": "背景色",
        "burn.settings_background_opacity": "背景の透明度",
        "burn.settings_background_size": "背景サイズ",
        "burn.settings_background_radius": "角丸サイズ",
        "burn.settings_max_chars": "1 行の最大文字数",
        "burn.settings_profile": "スタイル Profile",
        "burn.settings_profile_custom": "現在のスタイル",
        "burn.settings_profile_name": "Profile 名",
        "burn.settings_profile_name_placeholder": "例：会議字幕",
        "burn.settings_profile_save": "Profile を保存",
        "burn.settings_profile_delete": "Profile を削除",
        "burn.settings_preview": "ライブプレビュー",
        "burn.settings_preview_line_1": "これは字幕プレビューです",
        "burn.settings_preview_line_2": "ここで先に見た目を確認できます",
        "burn.settings_effects": "字幕効果",
        "burn.settings_shadow": "影を付ける",
        "burn.settings_background": "半透明背景を付ける",
        "burn.settings_submit": "焼き込み開始",
        "burn.settings_cancel": "キャンセル",
        "burn.settings_hint": "今後追加すると便利なのは、字幕位置、上下マージン、フォントファミリー、1 行あたりの最大文字数です。",
        "subtitle.editor_title": "SRT 字幕を編集",
        "subtitle.editor_intro": "この動画の SRT 字幕を修正し、保存後に字幕焼き込み MP4 を再生成できます。",
        "subtitle.editor_save": "字幕を保存",
        "subtitle.editor_cancel": "キャンセル",
        "subtitle.editor_placeholder": "ここで SRT 内容を編集してください",
        "subtitle.error.fetch": "字幕内容を読み込めません。",
        "subtitle.error.save": "字幕内容を保存できません。",
        "subtitle.error.missing": "この動画の SRT 字幕ファイルが見つかりません。",
        "delete_video.error.not_found": "削除対象の動画ファイルが見つかりません。",
        "delete_video.error.failed": "動画の削除に失敗しました。しばらくしてから再試行してください。",
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


def remove_video_index_entry(filename: str) -> None:
    index = load_video_index()
    if filename not in index:
        return
    del index[filename]
    save_video_index(index)


def resolve_video_filename(filename: str) -> Path | None:
    normalized_name = Path(filename).name
    if normalized_name != filename or not normalized_name.lower().endswith(".mp4"):
        return None

    target_path = (DOWNLOADS_DIR / normalized_name).resolve()
    try:
        target_path.relative_to(DOWNLOADS_DIR)
    except ValueError:
        return None
    return target_path


def delete_video_assets(filename: str) -> bool:
    video_path = resolve_video_filename(filename)
    if not video_path or not video_path.is_file():
        return False

    for transcript_path in TRANSCRIPTS_DIR.glob(f"{video_path.stem}.*"):
        if transcript_path.is_file():
            transcript_path.unlink(missing_ok=True)

    video_path.unlink()
    remove_video_index_entry(video_path.name)
    return True


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
        srt_path = TRANSCRIPTS_DIR / f"{path.stem}.srt"
        json_path = TRANSCRIPTS_DIR / f"{path.stem}.json"
        entry = index.get(path.name, {})
        transcript_downloads = {}
        for key, file_path in {
            "txt": txt_path,
            "srt": srt_path,
            "vtt": vtt_path,
            "json": json_path,
        }.items():
            if file_path.is_file():
                transcript_downloads[key] = {
                    "url": f"/transcripts/{file_path.name}",
                    "filename": file_path.name,
                }
        videos.append(
            {
                "filename": path.name,
                "title": entry.get("title") or path.stem,
                "uploader": entry.get("uploader"),
                "youtube_url": entry.get("webpage_url"),
                "source_type": entry.get("source_type"),
                "size_bytes": path.stat().st_size,
                "media_url": f"/media/{path.name}",
                "media_version": path.stat().st_mtime_ns,
                "download_url": f"/files/{path.name}",
                "transcript_downloads": transcript_downloads,
                "captions_url": f"/captions/{vtt_path.name}" if vtt_path.is_file() else None,
                "captions_version": vtt_path.stat().st_mtime_ns if vtt_path.is_file() else None,
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


def find_existing_downloaded_file(output_lines: list[str]) -> Path | None:
    pattern = re.compile(r"\[download\]\s+(?P<filename>.+?)\s+has already been downloaded")
    for line in reversed(output_lines):
        match = pattern.search(line)
        if not match:
            continue
        candidate = DOWNLOADS_DIR / match.group("filename").strip()
        if candidate.is_file():
            return candidate
    return None


def build_upload_filename(raw_title: str, original_filename: str) -> str:
    preferred_name = raw_title.strip() or Path(original_filename).stem or "uploaded-video"
    safe_stem = secure_filename(preferred_name) or f"uploaded-video-{uuid.uuid4().hex[:8]}"
    candidate = DOWNLOADS_DIR / f"{safe_stem}.mp4"
    suffix = 1
    while candidate.exists():
        candidate = DOWNLOADS_DIR / f"{safe_stem}-{suffix}.mp4"
        suffix += 1
    return candidate.name


def build_burned_video_filename(source_path: Path) -> str:
    safe_stem = secure_filename(f"{source_path.stem}-burned") or f"burned-video-{uuid.uuid4().hex[:8]}"
    candidate = DOWNLOADS_DIR / f"{safe_stem}.mp4"
    suffix = 1
    while candidate.exists():
        candidate = DOWNLOADS_DIR / f"{safe_stem}-{suffix}.mp4"
        suffix += 1
    return candidate.name


def copy_transcript_sidecars(source_stem: str, target_stem: str) -> None:
    for extension in ("txt", "srt", "vtt", "json"):
        source_path = TRANSCRIPTS_DIR / f"{source_stem}.{extension}"
        if not source_path.is_file():
            continue
        target_path = TRANSCRIPTS_DIR / f"{target_stem}.{extension}"
        shutil.copy2(source_path, target_path)


def get_srt_path_for_video(filename: str) -> Path:
    return TRANSCRIPTS_DIR / f"{Path(filename).stem}.srt"


def get_vtt_path_for_video(filename: str) -> Path:
    return TRANSCRIPTS_DIR / f"{Path(filename).stem}.vtt"


def normalize_hex_color(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", raw):
        return raw.lower()
    return fallback


def hex_to_ass_color(value: str, alpha: int = 0) -> str:
    red = int(value[1:3], 16)
    green = int(value[3:5], 16)
    blue = int(value[5:7], 16)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def ass_escape_text(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def ass_escape_path(path: Path) -> str:
    value = str(path)
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def srt_time_to_ass_timestamp(value: str) -> str:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, milliseconds = (int(part) for part in match.groups())
    centiseconds = int(round(milliseconds / 10))
    if centiseconds >= 100:
        seconds += 1
        centiseconds -= 100
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def parse_srt_entries(content: str) -> list[dict[str, Any]]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    entries: list[dict[str, Any]] = []
    blocks = re.split(r"\n\s*\n", normalized)
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n")]
        if len(lines) < 3:
            continue
        time_line = lines[1].strip() if "-->" in lines[1] else lines[0].strip()
        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        if "-->" not in time_line:
            continue
        parts = re.split(r"\s*-->\s*", time_line, maxsplit=1)
        if len(parts) != 2:
            continue
        start_raw, end_raw = parts
        cleaned_lines = [line.strip() for line in text_lines if line.strip()]
        if not cleaned_lines:
            continue
        entries.append(
            {
                "start": srt_time_to_ass_timestamp(start_raw),
                "end": srt_time_to_ass_timestamp(end_raw),
                "lines": cleaned_lines,
            }
        )
    return entries


@lru_cache(maxsize=8)
def resolve_font_file(font_name: str) -> str | None:
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", font_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    candidate = result.stdout.strip()
    return candidate if candidate and Path(candidate).is_file() else None


def get_font_metrics(font_name: str, font_size: float) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, ImageDraw.ImageDraw]:
    font_path = resolve_font_file(font_name)
    size = max(8, int(round(font_size)))
    if font_path:
        font = ImageFont.truetype(font_path, size=size)
    else:
        font = ImageFont.load_default()
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    return font, ImageDraw.Draw(image)


def measure_text_block(lines: list[str], font_name: str, font_size: float, outline_width: float, line_spacing: int) -> tuple[int, int]:
    font, draw = get_font_metrics(font_name, font_size)
    stroke_width = max(0, int(math.ceil(outline_width)))
    widths: list[int] = []
    heights: list[int] = []
    for line in lines:
        sample = line or " "
        left, top, right, bottom = draw.textbbox((0, 0), sample, font=font, stroke_width=stroke_width)
        widths.append(int(math.ceil(right - left)))
        heights.append(int(math.ceil(bottom - top)))
    if not widths:
        return 0, 0
    line_gap = max(0, line_spacing)
    return max(widths), sum(heights) + line_gap * max(0, len(lines) - 1)


def probe_video_dimensions(source_path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(source_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to read video dimensions.")
    payload = json.loads(result.stdout or "{}")
    stream = (payload.get("streams") or [{}])[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("Unable to determine video dimensions.")
    return width, height


def build_rounded_rectangle_path(width: int, height: int, radius: int) -> str:
    width = max(1, int(round(width)))
    height = max(1, int(round(height)))
    radius = max(0, min(int(round(radius)), width // 2, height // 2))
    if radius <= 0:
        return f"m 0 0 l {width} 0 l {width} {height} l 0 {height} c"
    kappa = 0.5522847498
    control = radius * kappa
    return " ".join(
        [
            f"m {radius} 0",
            f"l {width - radius} 0",
            f"b {width - radius + control:.2f} 0 {width:.2f} {radius - control:.2f} {width} {radius}",
            f"l {width} {height - radius}",
            f"b {width:.2f} {height - radius + control:.2f} {width - radius + control:.2f} {height:.2f} {width - radius} {height}",
            f"l {radius} {height}",
            f"b {radius - control:.2f} {height:.2f} 0 {height - radius + control:.2f} 0 {height - radius}",
            f"l 0 {radius}",
            f"b 0 {radius - control:.2f} {radius - control:.2f} 0 {radius} 0",
            "c",
        ]
    )


def build_ass_text_tags(parsed_settings: dict[str, Any], font_size: float) -> str:
    shadow_value = 0.8 if parsed_settings["shadow"] else 0
    return (
        f"\\fn{BURN_FONT_FAMILIES[parsed_settings['font_family']]}"
        f"\\fs{font_size:.1f}"
        "\\b1"
        f"\\1c{hex_to_ass_color(parsed_settings['text_color'])}"
        f"\\3c{hex_to_ass_color(parsed_settings['outline_color'])}"
        f"\\bord{parsed_settings['outline_width']}"
        f"\\shad{shadow_value}"
    )


def build_advanced_ass_content(subtitle_content: str, parsed_settings: dict[str, Any], video_width: int, video_height: int) -> str:
    entries = parse_srt_entries(subtitle_content)
    font_size = round(BURN_BASE_FONT_SIZE * BURN_FONT_SIZE_OPTIONS[parsed_settings["size"]], 1)
    font_name = BURN_FONT_FAMILIES[parsed_settings["font_family"]]
    horizontal_padding = (
        int(round(parsed_settings["background_size"] * BURN_BACKGROUND_HORIZONTAL_PADDING_FACTOR))
        if parsed_settings["background"]
        else 0
    )
    vertical_padding = (
        max(
            BURN_BACKGROUND_MIN_VERTICAL_PADDING,
            int(round(parsed_settings["background_size"] * BURN_BACKGROUND_VERTICAL_PADDING_FACTOR)),
        )
        if parsed_settings["background"]
        else 0
    )
    text_tags = build_ass_text_tags(parsed_settings, font_size)
    background_alpha = int(round(255 * (100 - parsed_settings["background_opacity"]) / 100))
    events: list[str] = []

    for entry in entries:
        line_width, text_height = measure_text_block(
            entry["lines"],
            font_name,
            font_size,
            parsed_settings["outline_width"],
            parsed_settings["line_spacing"],
        )
        scaled_line_width = max(1, int(round(line_width * BURN_BACKGROUND_WIDTH_SCALE)))
        box_width = scaled_line_width + horizontal_padding * 2
        box_height = text_height + vertical_padding * 2
        centered_x = int(round((video_width - box_width) / 2))
        box_x = max(parsed_settings["margin_l"], min(centered_x, video_width - parsed_settings["margin_r"] - box_width))
        if parsed_settings["position"] == "top":
            box_y = parsed_settings["margin_v"]
        elif parsed_settings["position"] == "middle":
            box_y = int(round((video_height - box_height) / 2))
        else:
            box_y = video_height - parsed_settings["margin_v"] - box_height
        box_x = max(0, box_x)
        box_y = max(0, box_y)

        if parsed_settings["background"]:
            path = build_rounded_rectangle_path(box_width, box_height, parsed_settings["background_radius"])
            background_tags = (
                f"{{\\an7\\pos({box_x},{box_y})\\p1\\bord0\\shad0"
                f"\\1c{hex_to_ass_color(parsed_settings['background_color'])}"
                f"\\1a&H{background_alpha:02X}&}}{path}{{\\p0}}"
            )
            events.append(
                f"Dialogue: 0,{entry['start']},{entry['end']},Default,,0,0,0,,{background_tags}"
            )

        line_y = box_y + vertical_padding
        text_x = box_x + int(round(box_width / 2))
        for line in entry["lines"]:
            text = ass_escape_text(line)
            events.append(
                f"Dialogue: 1,{entry['start']},{entry['end']},Default,,0,0,0,,"
                f"{{\\an8\\pos({text_x},{line_y}){text_tags}}}{text}"
            )
            _, rendered_height = measure_text_block(
                [line],
                font_name,
                font_size,
                parsed_settings["outline_width"],
                0,
            )
            line_y += rendered_height + parsed_settings["line_spacing"]

    script_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
        "",
    ]
    return "\n".join(script_lines)

def wrap_subtitle_text(text: str, max_chars_per_line: int) -> str:
    if max_chars_per_line <= 0:
        return text
    paragraphs = [segment.strip() for segment in text.splitlines()]
    wrapped_lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        wrapped_lines.extend(
            textwrap.wrap(
                paragraph,
                width=max_chars_per_line,
                break_long_words=True,
                break_on_hyphens=False,
                replace_whitespace=False,
                drop_whitespace=False,
            )
            or [paragraph]
        )
    return "\n".join(wrapped_lines)


def build_wrapped_srt_content(content: str, max_chars_per_line: int) -> str:
    if max_chars_per_line <= 0:
        return content
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized.strip())
    rebuilt_blocks: list[str] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            rebuilt_blocks.append(block)
            continue
        index_line = lines[0]
        time_line = lines[1]
        text = "\n".join(lines[2:])
        rebuilt_blocks.append("\n".join([index_line, time_line, wrap_subtitle_text(text, max_chars_per_line)]))
    return "\n\n".join(rebuilt_blocks).strip() + "\n"


def parse_burn_settings(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    size = str(payload.get("size", BURN_DEFAULT_SETTINGS["size"])).strip()
    font_family = str(payload.get("font_family", BURN_DEFAULT_SETTINGS["font_family"])).strip()
    text_color = normalize_hex_color(payload.get("text_color"), BURN_DEFAULT_SETTINGS["text_color"])
    outline_color = normalize_hex_color(payload.get("outline_color"), BURN_DEFAULT_SETTINGS["outline_color"])
    try:
        outline_width = float(payload.get("outline_width", BURN_DEFAULT_SETTINGS["outline_width"]))
    except (TypeError, ValueError):
        outline_width = BURN_DEFAULT_SETTINGS["outline_width"]
    position = str(payload.get("position", BURN_DEFAULT_SETTINGS["position"])).strip()
    try:
        line_spacing = int(payload.get("line_spacing", BURN_DEFAULT_SETTINGS["line_spacing"]))
    except (TypeError, ValueError):
        line_spacing = BURN_DEFAULT_SETTINGS["line_spacing"]
    try:
        margin_v = int(payload.get("margin_v", BURN_DEFAULT_SETTINGS["margin_v"]))
    except (TypeError, ValueError):
        margin_v = BURN_DEFAULT_SETTINGS["margin_v"]
    try:
        margin_l = int(payload.get("margin_l", BURN_DEFAULT_SETTINGS["margin_l"]))
    except (TypeError, ValueError):
        margin_l = BURN_DEFAULT_SETTINGS["margin_l"]
    try:
        margin_r = int(payload.get("margin_r", BURN_DEFAULT_SETTINGS["margin_r"]))
    except (TypeError, ValueError):
        margin_r = BURN_DEFAULT_SETTINGS["margin_r"]
    background_color = normalize_hex_color(payload.get("background_color"), BURN_DEFAULT_SETTINGS["background_color"])
    try:
        background_opacity = int(payload.get("background_opacity", BURN_DEFAULT_SETTINGS["background_opacity"]))
    except (TypeError, ValueError):
        background_opacity = BURN_DEFAULT_SETTINGS["background_opacity"]
    try:
        background_size = int(payload.get("background_size", BURN_DEFAULT_SETTINGS["background_size"]))
    except (TypeError, ValueError):
        background_size = BURN_DEFAULT_SETTINGS["background_size"]
    try:
        background_radius = int(payload.get("background_radius", BURN_DEFAULT_SETTINGS["background_radius"]))
    except (TypeError, ValueError):
        background_radius = BURN_DEFAULT_SETTINGS["background_radius"]
    try:
        max_chars_per_line = int(payload.get("max_chars_per_line", BURN_DEFAULT_SETTINGS["max_chars_per_line"]))
    except (TypeError, ValueError):
        max_chars_per_line = BURN_DEFAULT_SETTINGS["max_chars_per_line"]
    shadow = bool(payload.get("shadow", BURN_DEFAULT_SETTINGS["shadow"]))
    background = bool(payload.get("background", BURN_DEFAULT_SETTINGS["background"]))

    if size not in BURN_FONT_SIZE_OPTIONS:
        size = BURN_DEFAULT_SETTINGS["size"]
    if font_family not in BURN_FONT_FAMILIES:
        font_family = BURN_DEFAULT_SETTINGS["font_family"]
    if position not in BURN_POSITION_OPTIONS:
        position = BURN_DEFAULT_SETTINGS["position"]
    outline_width = max(0.0, min(6.0, outline_width))
    line_spacing = max(0, min(12, line_spacing))
    margin_v = max(8, min(96, margin_v))
    margin_l = max(0, min(160, margin_l))
    margin_r = max(0, min(160, margin_r))
    background_opacity = max(0, min(100, background_opacity))
    background_size = max(0, min(64, background_size))
    background_radius = max(0, min(40, background_radius))
    max_chars_per_line = max(0, min(48, max_chars_per_line))

    return {
        "size": size,
        "font_family": font_family,
        "text_color": text_color,
        "outline_color": outline_color,
        "outline_width": round(outline_width, 1),
        "position": position,
        "line_spacing": line_spacing,
        "margin_v": margin_v,
        "margin_l": margin_l,
        "margin_r": margin_r,
        "shadow": shadow,
        "background": background,
        "background_color": background_color,
        "background_opacity": background_opacity,
        "background_size": background_size,
        "background_radius": background_radius,
        "max_chars_per_line": max_chars_per_line,
    }


def srt_to_vtt_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    converted: list[str] = ["WEBVTT", ""]
    for line in lines:
        if "-->" in line:
            parts = re.split(r"\s*-->\s*", line, maxsplit=1)
            if len(parts) == 2:
                start = parts[0].replace(",", ".")
                end = parts[1].replace(",", ".")
                line = f"{start} --> {end}"
        converted.append(line)
    return "\n".join(converted).strip() + "\n"


def escape_ffmpeg_subtitle_path(path: Path) -> str:
    return ass_escape_path(path)


def build_subtitle_filter(subtitle_path: Path, settings: dict[str, Any] | None = None) -> str:
    parsed_settings = parse_burn_settings(settings)
    escaped_path = escape_ffmpeg_subtitle_path(subtitle_path)
    if subtitle_path.suffix.lower() == ".ass":
        return f"subtitles='{escaped_path}'"
    font_size = round(BURN_BASE_FONT_SIZE * BURN_FONT_SIZE_OPTIONS[parsed_settings["size"]], 1)
    alignment = BURN_POSITION_OPTIONS[parsed_settings["position"]]
    background_alpha = int(round(255 * (100 - parsed_settings["background_opacity"]) / 100))
    style_parts = [
        f"FontName={BURN_FONT_FAMILIES[parsed_settings['font_family']]}",
        f"FontSize={font_size}",
        f"PrimaryColour={hex_to_ass_color(parsed_settings['text_color'])}",
        f"OutlineColour={hex_to_ass_color(parsed_settings['outline_color'])}",
        f"Outline={parsed_settings['outline_width']}",
        f"Shadow={0.8 if parsed_settings['shadow'] else 0}",
        f"Alignment={alignment}",
        f"MarginV={parsed_settings['margin_v']}",
        f"MarginL={parsed_settings['margin_l']}",
        f"MarginR={parsed_settings['margin_r']}",
        f"LineSpacing={parsed_settings['line_spacing']}",
    ]
    if parsed_settings["background"]:
        style_parts.append("BorderStyle=4")
        style_parts.append(f"BackColour={hex_to_ass_color(parsed_settings['background_color'], background_alpha)}")
        style_parts.append("Shadow=4.2")
    return f"subtitles='{escaped_path}':force_style='{','.join(style_parts)}'"


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
            downloaded_file = find_existing_downloaded_file(output_lines)
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


def run_burned_video_job(job_id: str, filename: str, settings: dict[str, Any] | None = None) -> None:
    source_path = DOWNLOADS_DIR / filename
    subtitle_path = TRANSCRIPTS_DIR / f"{source_path.stem}.srt"
    parsed_settings = parse_burn_settings(settings)
    prepared_subtitle_path = subtitle_path
    prepared_filter_path = subtitle_path
    temp_dir: Path | None = None

    if not source_path.is_file():
        update_job(
            job_id,
            status="error",
            progress=0.0,
            status_key="burn.failed",
            status_text="",
            error="Source MP4 file not found.",
            error_key="burn.error.source_missing",
        )
        return

    if not subtitle_path.is_file():
        update_job(
            job_id,
            status="error",
            progress=0.0,
            status_key="burn.failed",
            status_text="",
            error="SRT subtitle file not found.",
            error_key="burn.error.subtitle_missing",
        )
        return

    if not ffmpeg_exists():
        update_job(
            job_id,
            status="error",
            progress=0.0,
            status_key="burn.failed",
            status_text="",
            error="ffmpeg is required to create a subtitle-burned MP4.",
            error_key="burn.error.ffmpeg_missing",
        )
        return

    target_filename = build_burned_video_filename(source_path)
    target_path = DOWNLOADS_DIR / target_filename
    if parsed_settings["max_chars_per_line"] > 0 or parsed_settings["background"]:
        temp_dir = Path(tempfile.mkdtemp(prefix="youtube-to-mp4-burn-"))
    if parsed_settings["max_chars_per_line"] > 0 and temp_dir:
        prepared_subtitle_path = temp_dir / subtitle_path.name
        prepared_subtitle_path.write_text(
            build_wrapped_srt_content(subtitle_path.read_text(encoding="utf-8"), parsed_settings["max_chars_per_line"]),
            encoding="utf-8",
        )
    if temp_dir:
        video_width, video_height = probe_video_dimensions(source_path)
        ass_path = temp_dir / f"{subtitle_path.stem}.ass"
        ass_path.write_text(
            build_advanced_ass_content(
                prepared_subtitle_path.read_text(encoding="utf-8"),
                parsed_settings,
                video_width,
                video_height,
            ),
            encoding="utf-8",
        )
        prepared_filter_path = ass_path
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vf",
        build_subtitle_filter(prepared_filter_path, parsed_settings),
        "-c:a",
        "copy",
        str(target_path),
    ]

    try:
        update_job(job_id, status="running", progress=5.0, status_key="burn.preparing", status_text="")
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE_DIR,
            check=False,
        )
        if completed.returncode != 0:
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            update_job(
                job_id,
                status="error",
                progress=0.0,
                status_key="burn.failed",
                status_text="",
                error=lines[-1] if lines else "Unable to create subtitle-burned MP4.",
                error_key=None,
            )
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            return

        if not target_path.is_file():
            update_job(
                job_id,
                status="error",
                progress=0.0,
                status_key="burn.failed",
                status_text="",
                error="The burned MP4 finished, but the new output file could not be found.",
                error_key="burn.error.output_missing",
            )
            return

        copy_transcript_sidecars(source_path.stem, target_path.stem)
        source_entry = load_video_index().get(source_path.name, {})
        burned_title = f"{source_entry.get('title') or source_path.stem} (Burned Subtitles)"
        upsert_video_index_entry(
            target_filename,
            {
                "title": burned_title,
                "uploader": source_entry.get("uploader"),
                "webpage_url": source_entry.get("webpage_url"),
                "video_id": source_entry.get("video_id"),
                "source_type": "burned_subtitles",
                "source_filename": source_path.name,
            },
        )
        update_job(
            job_id,
            status="completed",
            progress=100.0,
            status_key="burn.completed",
            status_text="",
            title=burned_title,
            filename=target_filename,
            error=None,
            error_key=None,
        )
    except Exception as exc:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        update_job(
            job_id,
            status="error",
            progress=0.0,
            status_key="burn.failed",
            status_text="",
            error=str(exc),
            error_key=None,
        )
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


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


def build_api_spec() -> dict[str, Any]:
    server_url = request.url_root.rstrip("/")
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "YouTube to MP4 Agent API",
            "version": API_VERSION,
            "description": (
                "HTTP API for AI agents and external platforms to submit YouTube download jobs, "
                "inspect files, and trigger speech-to-text transcription."
            ),
        },
        "servers": [{"url": server_url}],
        "tags": [
            {"name": "System", "description": "Service discovery and runtime capability endpoints."},
            {"name": "Downloads", "description": "Create and inspect asynchronous download jobs."},
            {"name": "Videos", "description": "List downloaded MP4 files and related transcript artifacts."},
            {"name": "Transcriptions", "description": "Create and inspect speech-to-text jobs."},
            {"name": "Burned Videos", "description": "Generate a new MP4 with subtitles burned into the video frames."},
        ],
        "paths": {
            "/api/health": {
                "get": {
                    "tags": ["System"],
                    "summary": "Service health check",
                    "responses": {
                        "200": {
                            "description": "Current service readiness and runtime dependency state.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/capabilities": {
                "get": {
                    "tags": ["System"],
                    "summary": "Agent capability discovery",
                    "responses": {
                        "200": {
                            "description": "Supported operations, models, and output capabilities.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CapabilitiesResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/downloads": {
                "post": {
                    "tags": ["Downloads"],
                    "summary": "Create a new YouTube download job",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateDownloadRequest"},
                                "examples": {
                                    "default": {
                                        "value": {
                                            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                            "quality": "720p",
                                        }
                                    }
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Download job accepted.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CreateDownloadResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request payload.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/jobs/{job_id}": {
                "get": {
                    "tags": ["Downloads"],
                    "summary": "Get download job status",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "job_id",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Current job snapshot.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/DownloadJob"}
                                }
                            },
                        },
                        "404": {
                            "description": "Unknown job id.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/videos": {
                "get": {
                    "tags": ["Videos"],
                    "summary": "List downloaded videos",
                    "responses": {
                        "200": {
                            "description": "Downloaded MP4 files with transcript metadata.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ListVideosResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/videos/{filename}": {
                "delete": {
                    "tags": ["Videos"],
                    "summary": "Delete a downloaded video and its transcript files",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "filename",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Video, transcript files, and index entry deleted.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/DeleteVideoResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Video file not found.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/transcriptions": {
                "post": {
                    "tags": ["Transcriptions"],
                    "summary": "Create a transcription job for an existing MP4",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateTranscriptionRequest"},
                                "examples": {
                                    "default": {
                                        "value": {
                                            "filename": "example-video.mp4",
                                            "model": "small",
                                        }
                                    }
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Transcription job accepted.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TranscriptionJob"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request payload.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/transcriptions/{job_id}": {
                "get": {
                    "tags": ["Transcriptions"],
                    "summary": "Get transcription job status",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "job_id",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Current transcription job snapshot.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TranscriptionJob"}
                                }
                            },
                        },
                        "404": {
                            "description": "Unknown transcription job id.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/burned-videos": {
                "post": {
                    "tags": ["Burned Videos"],
                    "summary": "Create a subtitle-burned MP4 from an existing video",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateBurnedVideoRequest"},
                                "examples": {
                                    "default": {
                                        "value": {
                                            "filename": "example-video.mp4",
                                        }
                                    }
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Burn job accepted.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CreateDownloadResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request payload.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/subtitles/{filename}": {
                "get": {
                    "tags": ["Videos"],
                    "summary": "Get editable SRT subtitle content for a video",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "filename",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Current SRT subtitle content.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SubtitleContentResponse"}
                                }
                            },
                        }
                    },
                },
                "put": {
                    "tags": ["Videos"],
                    "summary": "Save edited SRT subtitle content for a video",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "filename",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/UpdateSubtitleContentRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Updated subtitle content snapshot.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SubtitleContentResponse"}
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "error_key": {"type": "string"},
                    },
                    "required": ["error"],
                },
                "HealthResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "ok"},
                        "service": {"type": "string", "example": "youtube-to-mp4"},
                        "version": {"type": "string", "example": API_VERSION},
                        "yt_dlp_ready": {"type": "boolean"},
                        "ffmpeg_ready": {"type": "boolean"},
                        "stt_api_url": {"type": "string"},
                        "stt_reachable": {"type": "boolean"},
                    },
                    "required": [
                        "status",
                        "service",
                        "version",
                        "yt_dlp_ready",
                        "ffmpeg_ready",
                        "stt_api_url",
                        "stt_reachable",
                    ],
                },
                "CapabilitiesResponse": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "version": {"type": "string"},
                        "api_version": {"type": "string"},
                        "download_qualities": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(QUALITY_OPTIONS.keys())},
                        },
                        "transcription_models": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(TRANSCRIPTION_MODELS.keys())},
                        },
                        "features": {
                            "type": "object",
                            "properties": {
                                "download": {"type": "boolean"},
                                "video_listing": {"type": "boolean"},
                                "transcription": {"type": "boolean"},
                                "burned_video": {"type": "boolean"},
                                "swagger_docs": {"type": "boolean"},
                                "cli": {"type": "boolean"},
                            },
                            "required": ["download", "video_listing", "transcription", "burned_video", "swagger_docs", "cli"],
                        },
                    },
                    "required": [
                        "service",
                        "version",
                        "api_version",
                        "download_qualities",
                        "transcription_models",
                        "features",
                    ],
                },
                "CreateDownloadRequest": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "format": "uri"},
                        "quality": {"type": "string", "enum": list(QUALITY_OPTIONS.keys()), "default": "best"},
                    },
                    "required": ["url"],
                },
                "CreateDownloadResponse": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "status_url": {"type": "string"},
                    },
                    "required": ["job_id", "status_url"],
                },
                "DownloadJob": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "status": {"type": "string", "enum": ["queued", "running", "completed", "error"]},
                        "progress": {"type": "number"},
                        "status_key": {"type": "string"},
                        "status_text": {"type": "string"},
                        "title": {"type": "string", "nullable": True},
                        "filename": {"type": "string", "nullable": True},
                        "warning": {"type": "string", "nullable": True},
                        "warning_keys": {"type": "array", "items": {"type": "string"}},
                        "error": {"type": "string", "nullable": True},
                        "error_key": {"type": "string", "nullable": True},
                        "quality": {"type": "string"},
                        "download_url": {"type": "string", "nullable": True},
                    },
                    "required": [
                        "id",
                        "status",
                        "progress",
                        "status_key",
                        "status_text",
                        "warning_keys",
                        "quality",
                    ],
                },
                "TranscriptDownloadMap": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "filename": {"type": "string"},
                        },
                        "required": ["url", "filename"],
                    },
                },
                "VideoFile": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "title": {"type": "string"},
                        "uploader": {"type": "string", "nullable": True},
                        "youtube_url": {"type": "string", "nullable": True},
                        "source_type": {"type": "string", "nullable": True},
                        "size_bytes": {"type": "integer"},
                        "media_url": {"type": "string"},
                        "download_url": {"type": "string"},
                        "transcript_downloads": {"$ref": "#/components/schemas/TranscriptDownloadMap"},
                        "captions_url": {"type": "string", "nullable": True},
                        "is_transcribed": {"type": "boolean"},
                    },
                    "required": [
                        "filename",
                        "title",
                        "size_bytes",
                        "media_url",
                        "download_url",
                        "transcript_downloads",
                        "is_transcribed",
                    ],
                },
                "ListVideosResponse": {
                    "type": "object",
                    "properties": {
                        "videos": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/VideoFile"},
                        }
                    },
                    "required": ["videos"],
                },
                "DeleteVideoResponse": {
                    "type": "object",
                    "properties": {
                        "deleted": {"type": "boolean"},
                        "filename": {"type": "string"},
                    },
                    "required": ["deleted", "filename"],
                },
                "CreateTranscriptionRequest": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "model": {"type": "string", "enum": list(TRANSCRIPTION_MODELS.keys()), "default": STT_DEFAULT_MODEL},
                    },
                    "required": ["filename"],
                },
                "CreateBurnedVideoRequest": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "style": {
                            "type": "object",
                            "properties": {
                                "size": {"type": "string", "enum": list(BURN_FONT_SIZE_OPTIONS.keys())},
                                "font_family": {"type": "string", "enum": list(BURN_FONT_FAMILIES.keys())},
                                "text_color": {"type": "string", "example": "#ffffff"},
                                "outline_color": {"type": "string", "example": "#000000"},
                                "outline_width": {"type": "number", "minimum": 0, "maximum": 6, "example": 0.8},
                                "position": {"type": "string", "enum": list(BURN_POSITION_OPTIONS.keys())},
                                "line_spacing": {"type": "integer", "minimum": 0, "maximum": 12},
                                "margin_v": {"type": "integer", "minimum": 8, "maximum": 96},
                                "margin_l": {"type": "integer", "minimum": 0, "maximum": 160},
                                "margin_r": {"type": "integer", "minimum": 0, "maximum": 160},
                                "shadow": {"type": "boolean"},
                                "background": {"type": "boolean"},
                                "background_color": {"type": "string", "example": "#000000"},
                                "background_opacity": {"type": "integer", "minimum": 0, "maximum": 100},
                                "background_size": {"type": "integer", "minimum": 0, "maximum": 64},
                                "background_radius": {"type": "integer", "minimum": 0, "maximum": 40},
                                "max_chars_per_line": {"type": "integer", "minimum": 0, "maximum": 48},
                            },
                        },
                    },
                    "required": ["filename"],
                },
                "UpdateSubtitleContentRequest": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                    },
                    "required": ["content"],
                },
                "SubtitleContentResponse": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "subtitle_filename": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["filename", "subtitle_filename", "content"],
                },
                "TranscriptionJob": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "status": {"type": "string"},
                        "filename": {"type": "string", "nullable": True},
                        "model": {"type": "string", "nullable": True},
                        "error": {"type": "string", "nullable": True},
                        "error_key": {"type": "string", "nullable": True},
                        "output_files": {"type": "object", "additionalProperties": {"type": "string"}},
                        "download_urls": {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                },
            }
        },
    }


def build_health_payload() -> dict[str, Any]:
    status_code, _ = stt_request("/health")
    return {
        "status": "ok",
        "service": "youtube-to-mp4",
        "version": API_VERSION,
        "yt_dlp_ready": yt_dlp_exists(),
        "ffmpeg_ready": ffmpeg_exists(),
        "stt_api_url": STT_API_URL,
        "stt_reachable": status_code == 200,
    }


def build_capabilities_payload() -> dict[str, Any]:
    return {
        "service": "youtube-to-mp4",
        "version": API_VERSION,
        "api_version": "v1",
        "download_qualities": list(QUALITY_OPTIONS.keys()),
        "transcription_models": list(TRANSCRIPTION_MODELS.keys()),
        "features": {
            "download": True,
            "video_listing": True,
            "transcription": True,
            "burned_video": True,
            "swagger_docs": True,
            "cli": True,
        },
    }


@app.get("/")
def index():
    return render_template(
        "index.html",
        yt_dlp_ready=yt_dlp_exists(),
        ffmpeg_ready=ffmpeg_exists(),
        quality_options=QUALITY_OPTIONS,
        transcription_models=TRANSCRIPTION_MODELS,
        translations=TRANSLATIONS,
        app_version=API_VERSION,
    )


@app.get("/api/health")
def health():
    return jsonify(build_health_payload())


@app.get("/api/capabilities")
def capabilities():
    return jsonify(build_capabilities_payload())


@app.get("/api/openapi.json")
def openapi_spec():
    return jsonify(build_api_spec())


@app.get("/api/docs")
def api_docs():
    return render_template("swagger.html", openapi_url="/api/openapi.json", app_version=API_VERSION)


@app.post("/api/v1/downloads")
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
        return jsonify({"job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}"})
    except ValueError as exc:
        return jsonify({"error": str(exc), "error_key": "error.invalid_url"}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc), "error_key": "error.start_download"}), 500


@app.get("/api/v1/jobs/<job_id>")
@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Download job not found.", "error_key": "error.job_not_found"}), 404

    if job.get("filename"):
        job["download_url"] = f"/files/{job['filename']}"
    return jsonify(job)


@app.get("/api/v1/videos")
@app.get("/api/videos")
def videos():
    return jsonify({"videos": list_video_files()})


@app.delete("/api/v1/videos/<path:filename>")
@app.delete("/api/videos/<path:filename>")
def delete_video(filename: str):
    try:
        deleted = delete_video_assets(filename)
    except OSError:
        return jsonify({"error": "Failed to delete video.", "error_key": "delete_video.error.failed"}), 500

    if not deleted:
        return jsonify({"error": "Video file not found.", "error_key": "delete_video.error.not_found"}), 404

    return jsonify({"deleted": True, "filename": Path(filename).name})


@app.post("/api/v1/uploads")
@app.post("/api/uploads")
def upload_video():
    file = request.files.get("file")
    title = str(request.form.get("title", "")).strip()
    model = str(request.form.get("model", STT_DEFAULT_MODEL)).strip() or STT_DEFAULT_MODEL

    if not file or not file.filename:
        return jsonify({"error": "MP4 file is required.", "error_key": "upload.error.file_required"}), 400

    if not title:
        return jsonify({"error": "Title is required.", "error_key": "upload.error.title_required"}), 400

    source_name = file.filename.strip()
    if not source_name.lower().endswith(".mp4"):
        return jsonify({"error": "Only MP4 files are supported.", "error_key": "upload.error.invalid_type"}), 400

    target_filename = build_upload_filename(title, source_name)
    target_path = DOWNLOADS_DIR / target_filename

    try:
        file.save(target_path)
        upsert_video_index_entry(
            target_filename,
            {
                "title": title,
                "uploader": None,
                "webpage_url": None,
                "source_type": "upload",
            },
        )
        status_code, data = stt_request("/jobs", method="POST", payload={"filename": target_filename, "model": model})
        if status_code >= 400:
            return jsonify(data), status_code

        return jsonify(
            {
                "filename": target_filename,
                "title": title,
                "transcription_job_id": data.get("job_id"),
                "video": next((item for item in list_video_files() if item["filename"] == target_filename), None),
            }
        ), 201
    except OSError:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        return jsonify({"error": "Failed to save uploaded MP4.", "error_key": "upload.error.save_failed"}), 500


@app.post("/api/v1/transcriptions")
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


@app.post("/api/v1/burned-videos")
@app.post("/api/burned-videos")
def create_burned_video():
    payload = request.get_json(silent=True) or {}
    filename = str(payload.get("filename", "")).strip()
    burn_settings = parse_burn_settings(payload.get("style"))

    if not filename:
        return jsonify({"error": "filename is required", "error_key": "burn.error.start"}), 400

    if not (DOWNLOADS_DIR / filename).is_file():
        return jsonify({"error": "Source MP4 file not found.", "error_key": "burn.error.source_missing"}), 404

    if not (TRANSCRIPTS_DIR / f"{Path(filename).stem}.srt").is_file():
        return jsonify({"error": "SRT subtitle file not found.", "error_key": "burn.error.subtitle_missing"}), 404

    if not ffmpeg_exists():
        return jsonify({"error": "ffmpeg is required to create a subtitle-burned MP4.", "error_key": "burn.error.ffmpeg_missing"}), 500

    job_id, _ = create_job()
    worker = threading.Thread(target=run_burned_video_job, args=(job_id, filename, burn_settings), daemon=True)
    worker.start()
    return jsonify({"job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}"})


@app.get("/api/v1/subtitles/<path:filename>")
@app.get("/api/subtitles/<path:filename>")
def get_subtitle_content(filename: str):
    source_path = DOWNLOADS_DIR / filename
    subtitle_path = get_srt_path_for_video(filename)

    if not source_path.is_file() or not subtitle_path.is_file():
        return jsonify({"error": "The SRT subtitle file could not be found for this video.", "error_key": "subtitle.error.missing"}), 404

    try:
        return jsonify(
            {
                "filename": filename,
                "subtitle_filename": subtitle_path.name,
                "content": subtitle_path.read_text(encoding="utf-8"),
            }
        )
    except OSError:
        return jsonify({"error": "Unable to load subtitle content.", "error_key": "subtitle.error.fetch"}), 500


@app.put("/api/v1/subtitles/<path:filename>")
@app.put("/api/subtitles/<path:filename>")
def update_subtitle_content(filename: str):
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content", ""))
    source_path = DOWNLOADS_DIR / filename
    subtitle_path = get_srt_path_for_video(filename)
    web_caption_path = get_vtt_path_for_video(filename)

    if not source_path.is_file() or not subtitle_path.is_file():
        return jsonify({"error": "The SRT subtitle file could not be found for this video.", "error_key": "subtitle.error.missing"}), 404

    try:
        subtitle_path.write_text(content, encoding="utf-8")
        web_caption_path.write_text(srt_to_vtt_content(content), encoding="utf-8")
        return jsonify(
            {
                "filename": filename,
                "subtitle_filename": subtitle_path.name,
                "content": content,
            }
        )
    except OSError:
        return jsonify({"error": "Unable to save subtitle content.", "error_key": "subtitle.error.save"}), 500


@app.get("/api/v1/transcriptions/<job_id>")
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


@app.get("/captions/<path:filename>")
def captions(filename: str):
    return send_from_directory(TRANSCRIPTS_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
