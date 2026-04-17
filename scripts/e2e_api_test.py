from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


DEFAULT_BASE_URL = "http://127.0.0.1:5000"
REQUIRED_ARTIFACTS = ("mp4", "txt", "srt", "vtt", "json")


class TestFailure(RuntimeError):
    pass


def api_request(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any, str]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib_request.Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=180) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return response.status, json.loads(body.decode("utf-8")), content_type
            return response.status, body, content_type
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise TestFailure(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
    except urllib_error.URLError as exc:
        raise TestFailure(f"{method} {path} failed: {exc.reason}") from exc


def wait_for_job(
    base_url: str,
    path: str,
    terminal_statuses: set[str],
    timeout_seconds: float,
    poll_interval: float,
) -> dict[str, Any]:
    started = time.time()
    while True:
        _, payload, _ = api_request(base_url, path)
        status = str(payload.get("status", "")).lower()
        progress = payload.get("progress")
        print(f"[poll] {path} status={status or 'unknown'} progress={progress}")
        if status in terminal_statuses:
            return payload
        if timeout_seconds > 0 and time.time() - started > timeout_seconds:
            raise TestFailure(f"Timed out waiting for job {path}")
        time.sleep(poll_interval)


def preview_text(body: bytes, limit: int = 180) -> str:
    return body[:limit].decode("utf-8", errors="replace")


def validate_health(payload: dict[str, Any]) -> None:
    if payload.get("status") != "ok":
        raise TestFailure("Health check did not return status=ok")
    if not payload.get("yt_dlp_ready"):
        raise TestFailure("Health check reported yt-dlp is not ready")
    if not payload.get("stt_reachable"):
        raise TestFailure("Health check reported STT service is not reachable")


def validate_capabilities(payload: dict[str, Any]) -> None:
    features = payload.get("features", {})
    if not features.get("download"):
        raise TestFailure("Capabilities reported download=false")
    if not features.get("transcription"):
        raise TestFailure("Capabilities reported transcription=false")


def validate_video_entry(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    videos = payload.get("videos", [])
    matched = next((item for item in videos if item.get("filename") == filename), None)
    if not matched:
        raise TestFailure(f"Downloaded file {filename} was not found in /api/v1/videos")
    return matched


def fetch_artifact(base_url: str, path: str, name: str) -> dict[str, Any]:
    status, body, content_type = api_request(base_url, path)
    if status != 200:
        raise TestFailure(f"{name} download returned unexpected status {status}")
    if not isinstance(body, (bytes, bytearray)):
        body = json.dumps(body, ensure_ascii=False).encode("utf-8")

    result = {
        "ok": len(body) > 0,
        "status_code": status,
        "content_type": content_type,
        "size_bytes": len(body),
        "path": path,
    }
    if name != "mp4":
        result["preview"] = preview_text(body)
    return result


def run_test(args: argparse.Namespace) -> dict[str, Any]:
    results: dict[str, Any] = {
        "input": {
            "url": args.url,
            "base_url": args.base_url,
            "quality": args.quality,
            "model": args.model,
        },
        "steps": {},
        "artifacts": {},
    }

    print("[step] health check")
    status, health, _ = api_request(args.base_url, "/api/health")
    validate_health(health)
    results["steps"]["health"] = {"status_code": status, "payload": health}

    print("[step] capabilities")
    status, capabilities, _ = api_request(args.base_url, "/api/capabilities")
    validate_capabilities(capabilities)
    results["steps"]["capabilities"] = {"status_code": status, "payload": capabilities}

    print("[step] create download job")
    status, download_request, _ = api_request(
        args.base_url,
        "/api/v1/downloads",
        method="POST",
        payload={"url": args.url, "quality": args.quality},
    )
    download_job_id = download_request.get("job_id")
    if not download_job_id:
        raise TestFailure("Download API did not return job_id")
    results["steps"]["create_download"] = {"status_code": status, "payload": download_request}

    print("[step] wait for download")
    download_job = wait_for_job(
        args.base_url,
        f"/api/v1/jobs/{download_job_id}",
        {"completed", "error"},
        args.download_timeout,
        args.poll_interval,
    )
    results["steps"]["download_job"] = download_job
    if download_job.get("status") != "completed":
        raise TestFailure(f"Download job failed: {download_job.get('error')}")

    filename = str(download_job.get("filename") or "").strip()
    if not filename:
        raise TestFailure("Download job completed without filename")

    print("[step] list videos")
    status, videos_payload, _ = api_request(args.base_url, "/api/v1/videos")
    video_entry = validate_video_entry(filename, videos_payload)
    results["steps"]["videos"] = {"status_code": status, "matched_entry": video_entry}

    print("[step] create transcription job")
    status, transcription_request, _ = api_request(
        args.base_url,
        "/api/v1/transcriptions",
        method="POST",
        payload={"filename": filename, "model": args.model},
    )
    transcription_job_id = transcription_request.get("job_id") or transcription_request.get("id")
    if not transcription_job_id:
        raise TestFailure("Transcription API did not return job id")
    results["steps"]["create_transcription"] = {"status_code": status, "payload": transcription_request}

    print("[step] wait for transcription")
    transcription_job = wait_for_job(
        args.base_url,
        f"/api/v1/transcriptions/{transcription_job_id}",
        {"completed", "error", "failed"},
        args.transcription_timeout,
        args.poll_interval,
    )
    results["steps"]["transcription_job"] = transcription_job
    if str(transcription_job.get("status", "")).lower() != "completed":
        raise TestFailure(f"Transcription job failed: {transcription_job.get('error')}")

    artifact_paths = {"mp4": download_job.get("download_url")}
    for key, value in transcription_job.get("download_urls", {}).items():
        artifact_paths[key] = value

    missing = [name for name in REQUIRED_ARTIFACTS if not artifact_paths.get(name)]
    if missing:
        raise TestFailure(f"Missing artifact URLs for: {', '.join(missing)}")

    print("[step] download artifacts")
    for name in REQUIRED_ARTIFACTS:
        results["artifacts"][name] = fetch_artifact(args.base_url, artifact_paths[name], name)

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="End-to-end API test for YouTube download and transcription flows")
    parser.add_argument("--url", required=True, help="YouTube URL to test")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--quality", default="best", choices=["best", "1080p", "720p", "360p"])
    parser.add_argument("--model", default="small", choices=["small", "medium"])
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--download-timeout", type=float, default=900.0, help="Download timeout in seconds")
    parser.add_argument("--transcription-timeout", type=float, default=1800.0, help="Transcription timeout in seconds")
    parser.add_argument("--summary-only", action="store_true", help="Print a short human-readable summary")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        results = run_test(args)
    except TestFailure as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.summary_only:
        download_job = results["steps"]["download_job"]
        transcription_job = results["steps"]["transcription_job"]
        print("[pass] end-to-end flow completed")
        print(f"download filename: {download_job['filename']}")
        print(f"download status: {download_job['status']}")
        print(f"transcription status: {transcription_job['status']}")
        for name in REQUIRED_ARTIFACTS:
            artifact = results["artifacts"][name]
            print(f"{name}: {artifact['status_code']} {artifact['size_bytes']} bytes")
        return 0

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
