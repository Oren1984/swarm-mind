# Video validation report

File: [`showcase/video/swarm-mind-demo.mp4`](../../showcase/video/swarm-mind-demo.mp4). Machine-readable report written by the build: [`showcase/video/validation.json`](../../showcase/video/validation.json). Checked on 9 October 2026.

## How it was validated — and how it was not

The checks below are **measurements made by tools** (FFprobe, a full FFmpeg decode, audio analysis, pixel counts) plus my **visual inspection of 14 extracted frames**. I am an AI system working through a terminal: **I did not watch the video play and I did not listen to the audio.** Whether the narration sounds natural, whether the music is pleasant, and whether the pacing feels right have not been judged by a human. A human review before publishing is recommended.

## Results

| Check | Method | Result |
|---|---|---|
| MP4 opens and decodes | `ffprobe`; complete decode with `ffmpeg -v error -f null` | Container and both streams read; **zero decode errors** over the whole file. Not opened in a desktop media player. |
| Duration | `ffprobe` | **118.9 s** (target 90–120 s) |
| Video stream | `ffprobe` | H.264, 1920×1080, 30 fps, yuv420p, 3,567 frames |
| Audio stream | `ffprobe` | AAC, 44.1 kHz, stereo |
| File size | file system | 12.0 MB |
| Frames rendered correctly | Two frames per scene extracted and viewed (first and last sentence of each scene) | Title card, three recorded scenes of single worlds, the three-world dashboard, three charts and the closing card all appear as intended; no black or corrupt frames among those inspected. |
| Narration exists and is audible | Level analysis of the decoded audio | Mean level −18.7 dB, peak −1.0 dB; no stretch of one second or more below −50 dB anywhere in the file. |
| Narration is where the subtitles say | Cross-correlation of five source utterances against the final decoded audio | Each utterance found within **±4 ms** of its subtitle start time (cues at 0.7 s, 22.3 s, 51.2 s, 83.7 s, 113.3 s). |
| Music does not overpower narration | RMS of music versus RMS of speech in the mix | Music **21 dB below** speech (speech −19.8 dB, music −40.8 dB before final normalization). Not confirmed by listening. |
| Subtitles present | Bright-pixel count inside the subtitle band of each extracted frame | Text present in all 14 frames (3,100 to 9,100 bright pixels). |
| Subtitles synchronized | By construction (cue times are computed from the audio) and by the correlation check above | 21 cues for 21 utterances; no overlapping cues. |
| Subtitles readable | Cue statistics | Longest cue 125 characters on two lines; shortest cue on screen 3.1 s; highest reading rate 18.6 characters per second. |
| Captions do not cover metrics | Layout | The bottom 150 px are a reserved band; all footage and charts are scaled into the area above it. Confirmed in the inspected frames. |
| Subtitles match the narration | Same source text for both | Identical wording. One sentence is spelled phonetically for the speech engine only (the names Deneubourg and Dorigo). |
| Footage reflects the running system | Provenance | Clips are Playwright recordings of the Docker stack; step ranges are listed in [shot-list.md](shot-list.md). |
| No fictitious statistics | Build-time substitution from `summary.json` | Numbers used: 20 seeds; 60 agents; step 1,500; 1,279 and 561; 302, 275 and 654; 13 percent; 4 percent. Each matches the stored results (see [results-and-limitations.md](../results-and-limitations.md)). |

## Subtitle files

- [`captions-en.srt`](captions-en.srt) — 21 cues
- [`captions-en.vtt`](captions-en.vtt) — same content, WebVTT

The MP4 has the subtitles burned into the picture; it carries no separate subtitle track.

## Known issues

1. **No human playback or listening test** (see above). This is the main open item.
2. **Reading rate.** The fastest cue reaches 18.6 characters per second; common subtitle guidelines suggest staying nearer 17. It is one short sentence and stays on screen for its full spoken duration.
3. **Synthetic voice quality.** The Windows desktop voice is intelligible but clearly synthetic, and may mispronounce the researchers' names despite the phonetic spelling.
4. **Voice licensing is not verified** for public redistribution — see [music-license.md](music-license.md).
5. **Footage smoothness.** Clips were recorded at 25 fps by the browser recorder and resampled to 30 fps, so motion is less fluid than in the live dashboard.
6. **Simple music.** The bed is a basic synthesized pad.
7. **Scene timing differs from the original storyboard** (results scene longer, demonstration scenes shorter) — see [storyboard.md](storyboard.md).
8. On GitHub, an MP4 linked from a README opens in the file viewer rather than playing inline; it plays after clicking through or downloading.
