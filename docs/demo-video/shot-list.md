# Shot list

Every moving image in the video is a screen recording of the running dashboard (Docker stack, seed 1, default controlled scenario). Every chart is a file written by the experiment runner. The only composed graphics are the two text cards.

| Shot | Source file | How it was captured | Simulation steps shown | Speed setting | Used in scene |
|---|---|---|---|---|---|
| 1 | Title card | Text rendered over a blurred, darkened copy of `showcase/screenshots/hero-three-worlds.png` | — | — | 1 |
| 2 | `independent.webm` | Playwright screen recording, 1920×1080, focus mode "Independent", cropped to the world panel | from step 4 | 2× | 2 |
| 3 | `collective.webm` | Same, focus mode "Collective" | from step 4 | **4×** | 3 |
| 4 | `three-worlds.webm` | Same, "Compare all", uncropped (worlds, legend, live chart, table) | from step 522 | 2× | 4 |
| 5 | `breakdown.webm` | Same, focus mode "Breakdown"; the scheduled cut at step 1,500 occurs a few seconds in | from step 1,382 | 2× | 5 |
| 6 | `experiments/results/food_delivered_curves.png` | Written by `app.experiments.run` | 20-seed aggregate | — | 6 |
| 7 | `experiments/results/interruption_windows.png` | Written by `app.experiments.run` | 20-seed aggregate | — | 6 |
| 8 | `experiments/results/sensitivity.png` | Written by `app.experiments.run` | 20-seed aggregate | — | 6 |
| 9 | Closing card | Text over a blurred copy of `showcase/screenshots/world-collective-trails.png` | — | — | 7 |

## Honest notes on the footage

- **Speed.** The dashboard's speed selector was set to 2× for shots 2, 4 and 5 and to 4× for shot 3, so that trails are clearly formed within the 16 seconds of that scene. The footage itself is not sped up or slowed down in editing; what differs is how many simulation steps the app computes per rendered frame.
- **Starting later than step 0.** For shots 4 and 5 the session was first advanced to the start step through the public API without drawing (so no time is spent recording the wait), and the on-page Start button was then pressed. The recorded behaviour is the same deterministic run.
- **Recorder frame rate.** Playwright's recorder captures at 25 frames per second (VP9); clips were resampled to 30 fps for the final file. Motion is slightly less smooth than in a live browser, where the dashboard rendered at about 60 fps.
- **Step rate varies** with machine load during recording (roughly 20–50 steps per second). Different recordings of the same shot therefore cover different step ranges. The ranges above are those of the clips actually used.
- The raw clips are in the git-ignored `build/footage/` directory and can be regenerated with `node tools/record-footage.mjs`.
