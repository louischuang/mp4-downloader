from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


DEFAULT_BASE_URL = os.getenv("YTMP4_API_URL", "http://127.0.0.1:5000").rstrip("/")


class ApiError(RuntimeError):
    pass


def api_request(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib_request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {"error": body or str(exc)}
        raise ApiError(payload.get("error") or str(exc)) from exc
    except urllib_error.URLError as exc:
        raise ApiError(f"Unable to reach API server at {base_url}: {exc.reason}") from exc


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def wait_for_download(base_url: str, job_id: str, interval: float, timeout: float) -> dict[str, Any]:
    started = time.time()
    while True:
        payload = api_request(base_url, f"/api/v1/jobs/{job_id}")
        status = payload.get("status")
        if status in {"completed", "error"}:
            return payload
        if timeout > 0 and time.time() - started > timeout:
            raise ApiError(f"Timed out while waiting for download job {job_id}")
        time.sleep(interval)


def wait_for_transcription(base_url: str, job_id: str, interval: float, timeout: float) -> dict[str, Any]:
    started = time.time()
    while True:
        payload = api_request(base_url, f"/api/v1/transcriptions/{job_id}")
        status = str(payload.get("status", "")).lower()
        if status in {"completed", "error", "failed"}:
            return payload
        if timeout > 0 and time.time() - started > timeout:
            raise ApiError(f"Timed out while waiting for transcription job {job_id}")
        time.sleep(interval)


def cmd_health(args: argparse.Namespace) -> int:
    payload = api_request(args.base_url, "/api/health")
    print_payload(payload, args.json)
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    payload = api_request(args.base_url, "/api/capabilities")
    print_payload(payload, args.json)
    return 0


def cmd_videos(args: argparse.Namespace) -> int:
    payload = api_request(args.base_url, "/api/v1/videos")
    print_payload(payload, args.json)
    return 0


def cmd_job(args: argparse.Namespace) -> int:
    payload = api_request(args.base_url, f"/api/v1/jobs/{args.job_id}")
    print_payload(payload, args.json)
    return 0


def cmd_transcription_status(args: argparse.Namespace) -> int:
    payload = api_request(args.base_url, f"/api/v1/transcriptions/{args.job_id}")
    print_payload(payload, args.json)
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    payload = api_request(
        args.base_url,
        "/api/v1/transcriptions",
        method="POST",
        payload={"filename": args.filename, "model": args.model},
    )

    job_id = payload.get("job_id")
    if args.wait and job_id:
        payload = wait_for_transcription(args.base_url, job_id, args.interval, args.timeout)

    print_payload(payload, args.json)
    status = str(payload.get("status", "")).lower()
    return 1 if status in {"error", "failed"} else 0


def cmd_download(args: argparse.Namespace) -> int:
    payload = api_request(
        args.base_url,
        "/api/v1/downloads",
        method="POST",
        payload={"url": args.url, "quality": args.quality},
    )

    job_id = payload.get("job_id")
    if args.wait and job_id:
        payload = wait_for_download(args.base_url, job_id, args.interval, args.timeout)

    if args.transcribe:
        if not payload.get("filename"):
            raise ApiError("Download finished without a filename, cannot start transcription.")
        transcription = api_request(
            args.base_url,
            "/api/v1/transcriptions",
            method="POST",
            payload={"filename": payload["filename"], "model": args.model},
        )
        if args.wait and transcription.get("job_id"):
            transcription = wait_for_transcription(args.base_url, transcription["job_id"], args.interval, args.timeout)
        payload = {
            "download": payload,
            "transcription": transcription,
        }

    print_payload(payload, args.json)

    if "download" in payload:
        download_status = str(payload["download"].get("status", "")).lower()
        transcription_status = str(payload["transcription"].get("status", "")).lower()
        return 1 if download_status == "error" or transcription_status in {"error", "failed"} else 0

    return 1 if str(payload.get("status", "")).lower() == "error" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI for the YouTube to MP4 Agent API",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Check API health")
    health_parser.set_defaults(func=cmd_health)

    capabilities_parser = subparsers.add_parser("capabilities", help="List API capabilities")
    capabilities_parser.set_defaults(func=cmd_capabilities)

    videos_parser = subparsers.add_parser("videos", help="List downloaded videos")
    videos_parser.set_defaults(func=cmd_videos)

    job_parser = subparsers.add_parser("job", help="Inspect a download job")
    job_parser.add_argument("job_id", help="Download job id")
    job_parser.set_defaults(func=cmd_job)

    transcription_status_parser = subparsers.add_parser("transcription-status", help="Inspect a transcription job")
    transcription_status_parser.add_argument("job_id", help="Transcription job id")
    transcription_status_parser.set_defaults(func=cmd_transcription_status)

    download_parser = subparsers.add_parser("download", help="Create a download job")
    download_parser.add_argument("url", help="YouTube URL")
    download_parser.add_argument("--quality", default="best", choices=["best", "1080p", "720p", "360p"])
    download_parser.add_argument("--wait", action="store_true", help="Wait until the download finishes")
    download_parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    download_parser.add_argument("--timeout", type=float, default=600.0, help="Wait timeout in seconds, 0 disables timeout")
    download_parser.add_argument("--transcribe", action="store_true", help="Start transcription after download completes")
    download_parser.add_argument("--model", default="small", choices=["small", "medium"], help="Transcription model")
    download_parser.set_defaults(func=cmd_download)

    transcribe_parser = subparsers.add_parser("transcribe", help="Create a transcription job")
    transcribe_parser.add_argument("filename", help="Downloaded MP4 filename")
    transcribe_parser.add_argument("--model", default="small", choices=["small", "medium"])
    transcribe_parser.add_argument("--wait", action="store_true", help="Wait until the transcription finishes")
    transcribe_parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    transcribe_parser.add_argument("--timeout", type=float, default=1200.0, help="Wait timeout in seconds, 0 disables timeout")
    transcribe_parser.set_defaults(func=cmd_transcribe)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
