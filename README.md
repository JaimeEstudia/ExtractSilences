# ExtractSilences
# Silence Detector

A desktop application for detecting and labeling silence segments in MP4 videos.

---

## Requirements

- **Python 3.9+** (comes with Tkinter)
- **ffmpeg** — must be installed and available on your system PATH

---

## Installation

### 1. Install ffmpeg (Windows)

Download from https://ffmpeg.org/download.html or use winget:

```
winget install ffmpeg
```

Verify it works:
```
ffmpeg -version
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `opencv-python` — video decoding and frame rendering
- `Pillow` — image handling for Tkinter canvas
- `pydub` — audio extraction and silence detection (uses ffmpeg internally)

---

## Running the App

```bash
python app.py
```

---

## Features

| Feature | Description |
|---|---|
| 📁 Video Library | Upload and manage MP4 files; persisted in a local SQLite database |
| 🔇 Silence Detection | Configurable min/max duration and noise threshold (dBFS) |
| 🎬 Video Player | Frame-by-frame playback with play/pause/seek controls |
| 📊 Timeline | Visual timeline with silence segments shown as colored bars |
| 🏷 Segment Labels | Click any segment to jump to it; type a custom label inline |
| 🔄 Reprocess | Change parameters and click Analyze again on any loaded video |
| ⬇ CSV Export | Export all segments with labels, timestamps, and durations |

---

## Parameters

| Parameter | Default | Description |
|---|---|---|
| Min silence duration | 1.0 s | Segments shorter than this are ignored |
| Max silence duration | 60.0 s | Segments longer than this are ignored |
| Noise threshold | -40 dBFS | Audio below this level is considered silence |

**Threshold guidance:**
- `-40 dBFS` — good default for speech/interviews
- `-50 dBFS` — stricter (only very quiet sections)
- `-30 dBFS` — more permissive (includes soft background noise)

---

## Data Storage

All data is stored in: `~/.silence_detector.db` (SQLite)

This includes video paths, detected segments, and your custom labels.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "pydub not installed" | Run `pip install pydub` |
| "ffmpeg not found" | Install ffmpeg and ensure it's on PATH |
| "opencv not installed" | Run `pip install opencv-python pillow` |
| "Cannot open video file" | Ensure the file path still exists and is a valid MP4 |
| No segments found | Try lowering the threshold (e.g. -35) or reducing min duration |
