# Bug Report

Updated: 2026-04-18

## Fixed

- [x] Video playback breaks when playing the same video again or switching to another video in the player modal.
- [x] After editing subtitles, the in-browser video player still shows old captions instead of the updated subtitle content.
- [x] Burned subtitle MP4 output should use larger subtitles, a thinner black outline, and no shadow effect.

## Notes

- The player now rebuilds the subtitle track on each open/close cycle to avoid stale track state.
- Saving edited subtitles now updates both `srt` and `vtt`, so playback preview and burned MP4 use the same latest subtitle text.
- Burned subtitle styling was adjusted to improve readability while reducing heavy outline/shadow effects.
