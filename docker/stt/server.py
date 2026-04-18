from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel
from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename


INPUT_DIR = Path(os.getenv("STT_INPUT_DIR", "/data/input")).resolve()
OUTPUT_DIR = Path(os.getenv("STT_OUTPUT_DIR", "/data/output")).resolve()
MODEL_CACHE_DIR = os.getenv("HF_HOME", "/models/huggingface")
DEFAULT_MODEL = os.getenv("STT_DEFAULT_MODEL", "small")
DEVICE = os.getenv("STT_DEVICE", "cpu")
CPU_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE_CPU", "int8")
GPU_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE_GPU", "float16")

INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}
model_lock = threading.Lock()
loaded_models: dict[str, WhisperModel] = {}


def resolve_model_repo_name(model_name: str) -> str:
    if "/" in model_name:
        return model_name
    return f"Systran/faster-whisper-{model_name}"


def get_model_cache_state(model_name: str) -> dict[str, Any]:
    repo_name = resolve_model_repo_name(model_name)
    model_dir = Path(MODEL_CACHE_DIR) / f"models--{repo_name.replace('/', '--')}"
    if not model_dir.exists():
        return {
            "model_cache_bytes": 0,
            "model_download_incomplete_bytes": 0,
            "model_download_active": False,
        }

    cache_bytes = sum(path.stat().st_size for path in model_dir.rglob("*") if path.is_file())
    incomplete_bytes = sum(path.stat().st_size for path in model_dir.rglob("*.incomplete") if path.is_file())
    return {
        "model_cache_bytes": cache_bytes,
        "model_download_incomplete_bytes": incomplete_bytes,
        "model_download_active": incomplete_bytes > 0,
    }


def create_job(filename: str, model_name: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "status": "queued",
        "progress": 0.0,
        "status_key": "stt.queued",
        "status_text": "",
        "filename": filename,
        "model": model_name,
        "output_files": {},
        "error": None,
    }
    with jobs_lock:
        jobs[job_id] = job
    return job


def create_uploaded_job(filename: str, model_name: str, cleanup_source: bool) -> dict[str, Any]:
    job = create_job(filename, model_name)
    job["cleanup_source"] = cleanup_source
    return job


def update_job(job_id: str, **changes: Any) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job.update(changes)


def get_job(job_id: str) -> dict[str, Any] | None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return None
        snapshot = dict(job)

    if snapshot.get("status_key") == "stt.loading_model":
        snapshot.update(get_model_cache_state(str(snapshot.get("model", DEFAULT_MODEL))))
    return snapshot


def get_duration_seconds(file_path: Path) -> float | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(completed.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def get_model(model_name: str) -> WhisperModel:
    with model_lock:
        if model_name in loaded_models:
            return loaded_models[model_name]

        compute_type = GPU_COMPUTE_TYPE if DEVICE == "cuda" else CPU_COMPUTE_TYPE
        model = WhisperModel(
            model_name,
            device=DEVICE,
            compute_type=compute_type,
            download_root=MODEL_CACHE_DIR,
        )
        loaded_models[model_name] = model
        return model


def write_txt(path: Path, segments: list[dict[str, Any]]) -> None:
    text = "\n".join(segment["text"].strip() for segment in segments if segment["text"].strip())
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def format_srt_time(seconds: float) -> str:
    total_ms = int(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(path: Path, segments: list[dict[str, Any]]) -> None:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment["text"].strip()
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_time(segment['start'])} --> {format_srt_time(segment['end'])}",
                    text,
                ]
            )
        )
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def write_vtt(path: Path, segments: list[dict[str, Any]]) -> None:
    blocks: list[str] = ["WEBVTT\n"]
    for segment in segments:
        text = segment["text"].strip()
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    f"{format_srt_time(segment['start']).replace(',', '.')} --> {format_srt_time(segment['end']).replace(',', '.')}",
                    text,
                ]
            )
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def cleanup_source_file(job_id: str, source_path: Path) -> None:
    job = get_job(job_id) or {}
    if not job.get("cleanup_source"):
        return
    source_path.unlink(missing_ok=True)


def save_uploaded_source(uploaded_file: Any, requested_filename: str) -> str:
    original_name = str(requested_filename or getattr(uploaded_file, "filename", "")).strip()
    candidate_name = secure_filename(Path(original_name or "uploaded.mp4").name) or f"upload-{uuid.uuid4().hex}.mp4"
    if not candidate_name.lower().endswith(".mp4"):
        candidate_name = f"{Path(candidate_name).stem}.mp4"

    unique_name = candidate_name
    counter = 2
    while (INPUT_DIR / unique_name).exists():
        unique_name = f"{Path(candidate_name).stem}-{counter}.mp4"
        counter += 1

    target_path = INPUT_DIR / unique_name
    uploaded_file.save(target_path)
    return unique_name


def serialize_output_files(output_files: dict[str, str]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for file_type, filename in output_files.items():
        path = OUTPUT_DIR / filename
        if not path.is_file():
            continue
        artifacts[file_type] = {
            "filename": filename,
            "content": path.read_text(encoding="utf-8"),
        }
    return artifacts


def run_transcription(job_id: str, filename: str, model_name: str) -> None:
    source_path = INPUT_DIR / filename
    if not source_path.is_file():
        update_job(job_id, status="error", progress=0.0, status_key="stt.failed", error="Source MP4 file not found.")
        return

    try:
        update_job(job_id, status="running", progress=2.0, status_key="stt.loading_model")
        model = get_model(model_name)

        duration = get_duration_seconds(source_path)
        update_job(job_id, progress=6.0, status_key="stt.transcribing")
        segments_iter, info = model.transcribe(
            str(source_path),
            beam_size=5,
            vad_filter=True,
        )

        segments_data: list[dict[str, Any]] = []
        for segment in segments_iter:
            entry = {"start": segment.start, "end": segment.end, "text": segment.text}
            segments_data.append(entry)
            if duration and duration > 0:
                percent = min(92.0, max(6.0, (segment.end / duration) * 90.0))
                update_job(job_id, progress=percent, status_key="stt.transcribing")

        update_job(job_id, progress=94.0, status_key="stt.writing_files")
        stem = source_path.stem
        txt_path = OUTPUT_DIR / f"{stem}.txt"
        srt_path = OUTPUT_DIR / f"{stem}.srt"
        vtt_path = OUTPUT_DIR / f"{stem}.vtt"
        json_path = OUTPUT_DIR / f"{stem}.json"

        write_txt(txt_path, segments_data)
        write_srt(srt_path, segments_data)
        write_vtt(vtt_path, segments_data)
        json_path.write_text(
            json.dumps(
                {
                    "source_file": filename,
                    "model": model_name,
                    "language": info.language,
                    "duration": duration,
                    "segments": segments_data,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        update_job(
            job_id,
            status="completed",
            progress=100.0,
            status_key="stt.completed",
            output_files={
                "txt": txt_path.name,
                "srt": srt_path.name,
                "vtt": vtt_path.name,
                "json": json_path.name,
            },
            error=None,
        )
        cleanup_source_file(job_id, source_path)
    except Exception as exc:
        update_job(job_id, status="error", progress=0.0, status_key="stt.failed", error=str(exc))
        cleanup_source_file(job_id, source_path)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/jobs")
def create_transcription_job():
    uploaded_file = request.files.get("file")

    if uploaded_file:
        model_name = str(request.form.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        requested_filename = str(request.form.get("filename", uploaded_file.filename or "")).strip()
        try:
            filename = save_uploaded_source(uploaded_file, requested_filename)
        except OSError:
            return jsonify({"error": "failed to save uploaded file"}), 500
        job = create_uploaded_job(filename, model_name, cleanup_source=True)
    else:
        payload = request.get_json(silent=True) or {}
        filename = str(payload.get("filename", "")).strip()
        model_name = str(payload.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL

        if not filename:
            return jsonify({"error": "filename is required"}), 400
        job = create_uploaded_job(filename, model_name, cleanup_source=False)

    worker = threading.Thread(target=run_transcription, args=(job["id"], filename, model_name), daemon=True)
    worker.start()
    return jsonify({"job_id": job["id"]}), 202


@app.get("/jobs/<job_id>")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.get("/jobs/<job_id>/artifacts")
def job_artifacts(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    if job.get("status") != "completed":
        return jsonify({"error": "job not completed"}), 409

    output_files = job.get("output_files", {})
    return jsonify(
        {
            "job_id": job_id,
            "filename": job.get("filename"),
            "output_files": output_files,
            "artifacts": serialize_output_files(output_files),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
