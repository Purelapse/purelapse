# Purelapse

[Deutsch](README.md) · **English**

**Flicker-free timelapses – from RAW or JPG sequences, with ART, RawTherapee or Darktable.**

> ⚠️ **Beta version.** Purelapse is under active development. Please back up
> your original images and report bugs as an [issue](https://github.com/slvobng/purelapse/issues).

![Purelapse: filmstrip, brightness chart and settings](docs/screenshot.jpg)

**Before – after:** left untouched, right processed with Purelapse

https://github.com/user-attachments/assets/08c6d79c-24cf-44d8-aacb-35ddfd3aa6f2

## Contents

- [What Purelapse does](#what-purelapse-does)
- [Features at a glance](#features-at-a-glance)
- [Deflicker](#deflicker)
- [Holy grail: day-to-night transitions](#holy-grail-day-to-night-transitions)
- [Keyframes and quick settings](#keyframes-and-quick-settings)
- [Video output and quality](#video-output-and-quality)
- [Image and effects](#image-and-effects)
- [Analysis and warnings](#analysis-and-warnings)
- [Preview and comparison](#preview-and-comparison)
- [Queue and Telegram](#queue-and-telegram)
- [Performance](#performance)
- [User interface](#user-interface)
- [Installation (Linux)](#installation-linux)
- [Running from source](#running-from-source)
- [Building it yourself](#building-it-yourself)
- [Known limitations](#known-limitations)
- [License](#license)

## What Purelapse does

In timelapses with changing light (sunsets, holy grail, night shots) the
brightness jumps from frame to frame. Purelapse smooths this out in three
steps:

1. **Pass 1 – smooth brightness:** Purelapse measures the brightness of every
   RAW in linear light and writes an exposure correction into the engine's
   sidecar files (`.arp`, `.pp3` or `.xmp`).
2. **Keyframes (optional):** Grade individual frames – right inside Purelapse
   with the quick settings, or in the engine. Purelapse blends smoothly in
   between.
3. **Pass 2 – render video:** The engine develops all frames, Purelapse
   re-measures the result, corrects the remaining deviation in further rounds
   and creates the video.

JPG sequences are processed in a single pass, without an external engine.

## Features at a glance

| Area | Features |
|---|---|
| **Deflicker** | Measurement in linear light (16 bit), two-stage smoothing, recalibration until residual flicker is below 0.008 EV, measuring area (ROI), light progression sunrise/sunset/constant |
| **Holy grail** | Compensates exposure and ISO jumps, detects ramping intervals, EXIF exposure and sun elevation as curves |
| **RAW development** | ART, RawTherapee, Darktable; formats NEF, CR2, CR3, DNG, ARW, RAF, ORF, RW2, PEF, SRW |
| **Keyframes** | Smooth blending between keyframes, quick settings with a real engine preview, automatic optimisation, highlight reconstruction |
| **Video** | 720p to 8K, 23.976 to 120 fps, H.264, H.265, ProRes 422 HQ, CPU or NVIDIA, Intel QuickSync, VAAPI, four quality levels |
| **Effects** | Motion blur (3–25 frames), 16:9 camera move, stabilisation, denoise, hot pixels, astro clean, telemetry overlay, fade in/out, reverse |
| **Checks** | Quick preview, 5-frame preview, untouched version, comparison video, warnings for gaps and highlights |
| **Workflow** | Batch queue, Telegram notification, resume after cancelling, parallel processing |
| **Interface** | Step bar, progress display with timings, light and dark theme, German and English |

## Deflicker

- **Measurement in linear light.** RAWs are measured at 16 bit with gamma 1.0.
  This keeps the measurement reliable even in dark night shots, where an 8-bit
  measurement would merge large parts of the image into black.
- **Two-stage smoothing.** The *deflicker strength* slider sets how strongly
  the curve is smoothed: low values only remove fast flicker, high values also
  reshape the light progression. From 85 % on, the curve blends seamlessly
  into a straight regression line.
- **Light progression.** *Constant* keeps the progression as it is; *sunrise*
  and *sunset* enforce a progression that only gets brighter or only gets
  darker.
- **Exposure (EV).** Shifts the target brightness of the whole sequence by up
  to ±3 EV.
- **Measuring area (ROI).** Restricts the measurement to part of the frame –
  useful when the sun, lamps or moving objects disturb the measurement.
- **Recalibration.** After developing, Purelapse measures the engine's result,
  writes the remaining deviation back into the sidecar files and has them
  developed again – only the frames that actually changed. Up to three rounds;
  stops as soon as the residual flicker is below 0.008 EV.
- **Existing edits are kept.** Purelapse only sets the exposure in the
  profile. With Darktable it adds its own exposure module and leaves the
  existing edit history untouched.
- **JPG workflow.** JPG sequences are deflickered directly, without an engine,
  and can optionally be saved as single images without a video.

## Holy grail: day-to-night transitions

In holy-grail shots the camera changes shutter speed, aperture or ISO during
the sequence. Purelapse is built for this:

- **Compensating exposure jumps.** Because every RAW is measured in linear
  light, the jumps caused by changed camera settings show up as brightness
  steps – and the deflicker smooths them out.
- **Ramping interval.** If the shooting interval grows or shrinks with the
  shutter speed, Purelapse treats that as normal and only reports real gaps.
- **Curves for checking.** Besides brightness, the chart can show the EXIF
  exposure and the interval.
- **Sun elevation.** With latitude and longitude (or GPS from the image),
  Purelapse shows the sun elevation as a curve and marks the limits of civil,
  nautical and astronomical twilight – ideal for placing keyframes.

## Keyframes and quick settings

- **Keyframes.** Individual frames are marked as keyframes (5 stars) and
  graded in the engine or in Purelapse. When rendering, Purelapse carries the
  settings smoothly across all frames in between.
- **Quick settings** (ART and RawTherapee) right inside Purelapse via
  *Edit keyframe…*, without opening the engine:

  | Control | Range |
  |---|---|
  | Colour temperature | 2000 – 12000 K |
  | Green balance | 0.6 – 1.8 |
  | Brightness, contrast, saturation | −100 – +100 |
  | Sharpening | 1 – 1000 |
  | Denoise luminance / chrominance | 0 – 100 |

  Every control has its own checkbox: anything left unticked stays unchanged
  in the profile. Exposure is excluded – that belongs to the deflicker.
- **Real preview.** The engine develops the frame with the chosen values,
  with a histogram and *show before*.
- **Automatic optimisation.** Measures the frame and suggests brightness,
  contrast, saturation, sharpening and denoising (matched to the ISO value) –
  each with the reason the value is based on.
- **Copy from another keyframe.** Transfer the settings of one keyframe to
  another.
- **Highlight reconstruction.** Against the pink sun disc: recovers clipped
  colour channels from their surroundings (ART: Blend, Color, Balanced;
  RawTherapee: Blend, Color, Coloropp).
- **Keyframes only.** Filters the filmstrip down to the marked frames.

## Video output and quality

| Setting | Options |
|---|---|
| **Resolution (16:9)** | 720p (HD Ready), 1080p (Full HD), 1440p (2.5K), 2160p (4K), 4320p (8K) |
| **Frame rate** | 23.976 · 24 · 25 · 29.97 · 30 · 50 · 59.94 · 60 · 120 fps |
| **Quality** | Visually lossless (CRF 16) · High (CRF 20) · Standard (CRF 23) · Low (CRF 28) |
| **Fade in / out** | Off · 0.5 · 1 · 2 · 3 seconds from/to black |
| **Location** | Image folder, parent folder, program folder or a folder of your choice |
| **Existing file** | Create a new version (`_v1`, `_v2`, …) or overwrite |

**Video codecs:**

| Codec | Encoding | File |
|---|---|---|
| H.264 | CPU (libx264) | `.mp4` |
| H.264 | NVIDIA GPU (NVENC) | `.mp4` |
| H.264 | Intel QuickSync | `.mp4` |
| H.264 | VAAPI (AMD/Intel) | `.mp4` |
| H.265 / HEVC | CPU (libx265) | `.mp4` |
| H.265 / HEVC | NVIDIA GPU (NVENC) | `.mp4` |
| H.265 / HEVC | Intel QuickSync | `.mp4` |
| H.265 / HEVC | VAAPI (AMD/Intel) | `.mp4` |
| Apple ProRes 422 HQ | CPU | `.mov` |

- **Codec self-test.** Before every run Purelapse checks whether the chosen
  hardware codec works on this computer and otherwise offers the matching CPU
  codec.
- **Estimated file size** is shown before you start.

## Image and effects

- **Motion blur.** Averages 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18, 20 or 25
  frames into one video frame – for soft, cinematic movement of clouds, water
  and stars.
- **16:9 camera move / crop.** Set the framing for the first and the last
  frame; in between the camera moves smoothly from A to B. Without it, the
  frame is cropped to 16:9 around the centre.
- **Optical stabilisation.** Evens out shake between frames (costs a little
  of the frame edge).
- **Denoise.** Noise reduction, stronger at high ISO values.
- **Remove dead / hot pixels.** For RAW via the engine; for JPG, Purelapse
  looks for points that stand out at the same position throughout the
  sequence – stars and subject details stay untouched.
- **Astro clean.** Removes satellite trails by comparing every frame with its
  two neighbours.
- **Telemetry overlay.** Shows time, ISO, aperture and shutter speed in the
  video.
- **Render in reverse.** Plays the sequence backwards.
- **Start and end frame.** Limits the whole workflow to part of the sequence;
  saved per folder.

## Analysis and warnings

- **Brightness chart** with measured curve, target curve, keyframes and the
  selected frame; optional curves: white balance, exposure (EXIF), interval,
  clipping, residual flicker and sun elevation.
- **Gaps in the sequence.** Missing frames are detected from the capture times
  and shown with their position.
- **Clipped highlights.** Share of pixels that are at the sensor's limit, per
  frame.
- **Pink highlights.** Warns about the typical magenta sun disc and points to
  highlight reconstruction.
- **Fluctuating white balance** of the camera within the sequence is reported.
- **Diagnostic mode.** Optionally writes measurement logs (CSV) and check
  reports to the image folder.

## Preview and comparison

- **⚡ Quick preview.** A rough video in minutes instead of hours, built from
  the camera's embedded preview images, with the smoothing from the chart and
  the chosen framing (up to 1280 pixels wide).
- **Preview (5 frames).** Develops five frames spread across the sequence with
  all settings – saves a whole wasted run.
- **Untouched version.** The timelapse without any processing, as a reference.
- **Comparison video.** Places two finished videos side by side or as a split
  screen.

## Queue and Telegram

- **Queue.** Add several folders, each with its own settings, and have them
  processed one after another. Cancelling pauses the batch; the next start
  resumes at the same point.
- **Telegram notification.** When a run finishes or fails, Purelapse sends a
  message with the folder, the steps, their duration and the residual flicker.
  Purelapse finds the chat ID itself; a test message checks the connection.

## Performance

- **Parallel development.** Several engine processes with a few cores each
  instead of one process with all cores – much faster on many-core machines.
  *Automatic* adapts to the number of cores and the free memory.
- **Parallel measurement** on several cores.
- **Resume after cancelling.** Frames that were already developed and have not
  changed are not developed again.

## User interface

- **Step bar** guides you through load images → smooth brightness → edit
  keyframes → render video; completed steps are marked.
- **Start dialog** offers to continue the last workflow.
- **Progress display** with progress, remaining time and the duration of every
  step.
- **Log** with timestamps; opens by itself when an error occurs.
- **Reset** deletes selected working files in the image folder.
- **Engine detection.** If sidecar files already exist in the folder,
  Purelapse selects the matching engine itself.
- **Light and dark theme**, interface in **German and English**.

## Installation (Linux)

1. Install **RawTherapee** and/or **ART** (for RAW development).
2. Download `Purelapse-…-x86_64.AppImage` from
   [Releases](https://github.com/slvobng/purelapse/releases).
3. Make it executable and start it:
   ```bash
   chmod +x Purelapse-*-x86_64.AppImage
   ./Purelapse-*-x86_64.AppImage
   ```
4. In Purelapse, open **Settings…** and enter the path to `rawtherapee-cli` or
   `ART-cli`.

The AppImage contains Python, Qt, OpenCV, rawpy and FFmpeg. It runs on
Linux Mint 21 / Ubuntu 22.04 and newer. If a system FFmpeg is installed, it is
preferred (matching the graphics driver).

JPG sequences don't need an engine.

## Running from source

```bash
git clone https://github.com/slvobng/purelapse.git
cd purelapse
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python purelapse_main.py
```

## Building it yourself

Build the AppImage with `bash build_appimage.sh` (requires Docker and internet).

## Known limitations

- Darktable: quick settings, the real preview and hot pixel removal are only
  available for ART and RawTherapee.

## License

Purelapse is licensed under the [GNU General Public License v3](LICENSE).

Purelapse calls ART, RawTherapee, Darktable and FFmpeg as separate programs;
their own licenses apply to them. The AppImage contains an FFmpeg build from
the `imageio-ffmpeg` package.

Copyright (C) 2026 slvobng
