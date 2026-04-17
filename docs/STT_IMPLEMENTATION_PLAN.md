# STT Integration Plan

## Goal

Add a basic "video to text" workflow to the existing MP4 downloader by:

- running `faster-whisper` in a separate Docker container
- keeping the STT service independent from the main downloader service
- allowing the web UI to trigger transcription for downloaded MP4 files
- generating transcript output files for validation

This first version is focused on **basic validation on Mac M4**.

## Scope For First Validation

The first implementation should include:

- a separate STT container for Mac M4 validation
- a lightweight STT HTTP API
- shared input/output folders between app container and STT container
- a transcript job flow from the main web app
- UI controls to trigger transcription on downloaded videos
- transcript progress / status display
- transcript output file download link

The first implementation will **not** include:

- advanced editing of transcript text
- speaker diarization
- subtitle preview editor
- translation post-processing
- GPU runtime switching logic in the app UI

## Container Architecture

### Main App Container

Responsibilities:

- manage YouTube download jobs
- render the web UI
- show available downloaded MP4 files
- create transcription jobs
- poll / proxy transcription state

### STT Container

Responsibilities:

- accept a transcription request
- load `faster-whisper`
- read MP4 input from shared storage
- extract / decode audio using `ffmpeg`
- generate transcript files

### Shared Volumes

- `./video-storage` -> downloaded MP4 input files
- `./transcripts` -> generated transcript output
- `./models` -> Hugging Face / Whisper model cache

## Basic Runtime Design

### Input

- source MP4 file path from `video-storage`
- model name, initially default to `small`

### Output

Generate at least:

- `.txt`
- `.srt`
- optional `.json` metadata for debugging

### Recommended Naming

For a source file:

```text
video-storage/MyVideo.mp4
```

Output files:

```text
transcripts/MyVideo.txt
transcripts/MyVideo.srt
transcripts/MyVideo.json
```

## Web UI Changes

Add a transcript section that:

- lists existing downloaded MP4 files
- shows a `Transcribe` button for each file
- shows transcript progress and status
- shows links to generated transcript files

Optional first-version controls:

- transcript model selector with `small` default

## Execution Steps

1. Create a dedicated STT service directory and runtime code.
2. Build a simple HTTP API for transcription requests.
3. Add a shared transcript output directory.
4. Add STT service to Docker Compose for Mac M4 validation.
5. Add environment variable in main app for STT service URL.
6. Add backend job handling for transcript requests.
7. Add UI section for downloaded MP4 files and transcript actions.
8. Add polling and progress rendering for transcript jobs.
9. Add transcript output links in the UI.
10. Verify end-to-end flow on one MP4 file.

## Testing Checklist

### Build / Runtime

- main downloader container starts normally
- STT container starts normally
- STT container health endpoint responds
- shared volumes are mounted correctly

### Functional

- downloaded MP4 files appear in the UI
- clicking `Transcribe` creates a transcript job
- transcript job status changes from queued -> running -> completed
- transcript `.txt` file is generated
- transcript `.srt` file is generated
- generated files are downloadable from the UI

### Failure Handling

- missing MP4 file returns readable error
- STT service unavailable returns readable error
- failed transcription updates UI state correctly

### Mac M4 Validation

- `faster-whisper` runs in Docker on `linux/arm64`
- transcription completes with CPU inference
- model cache persists between container restarts

## First Version Success Criteria

The first validation is successful when:

- a downloaded MP4 can be transcribed from the browser
- transcript progress is visible
- `.txt` and `.srt` outputs are generated into `./transcripts`
- the flow works with the Mac M4 STT container

## Next Step After Validation

After the first validation passes, we can iterate on:

- selectable models (`small`, `medium`, `large-v3`)
- transcript history view
- better transcript preview UI
- GPU-target compose profile for x64 + NVIDIA
- optional auto-transcribe after download
