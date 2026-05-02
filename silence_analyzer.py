"""
Silence analysis engine.
Uses pydub (backed by ffmpeg) to extract audio and detect silence segments.
"""

import os
import sys
import subprocess
import tempfile
from typing import List, Dict


def check_dependencies() -> dict:
    """
    Probe each dependency independently.
    Returns a dict with keys: pydub, ffmpeg, ffmpeg_path, ffprobe, error
    """
    result = {
        "pydub": False,
        "audioop": True,  # assume fine unless Python >= 3.13
        "ffmpeg": False,
        "ffmpeg_path": None,
        "ffprobe": False,
        "error": None,
    }

    # 0. Python 3.13+ removed the built-in audioop module that pydub needs.
    #    audioop-lts is a drop-in backport that fixes this.
    py_ver = sys.version_info
    if py_ver >= (3, 13):
        try:
            import audioop  # noqa: F401

            result["audioop"] = True
        except ImportError:
            try:
                import audioop_lts  # noqa: F401 — some versions expose this name

                result["audioop"] = True
            except ImportError:
                result["audioop"] = False
    else:
        result["audioop"] = True  # built-in on 3.12 and below

    # 1. Check pydub import
    try:
        import pydub  # noqa: F401

        result["pydub"] = True
    except ImportError as e:
        result["error"] = f"pydub import failed: {e}"
        return result

    # 2. Check ffmpeg on PATH via subprocess (independent of pydub)
    for exe in ("ffmpeg", "ffmpeg.exe"):
        try:
            r = subprocess.run(
                [exe, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if r.returncode == 0:
                result["ffmpeg"] = True
                result["ffmpeg_path"] = exe
                break
        except (FileNotFoundError, OSError):
            continue
        except subprocess.TimeoutExpired:
            result["error"] = "ffmpeg found but timed out on -version"

    # 3. Check ffprobe (needed by pydub for some formats)
    for exe in ("ffprobe", "ffprobe.exe"):
        try:
            r = subprocess.run(
                [exe, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if r.returncode == 0:
                result["ffprobe"] = True
                break
        except (FileNotFoundError, OSError):
            continue

    # 4. Check pydub's own ffmpeg finder
    if result["pydub"] and not result["ffmpeg"]:
        try:
            from pydub.utils import which

            found = which("ffmpeg")
            if found:
                result["ffmpeg"] = True
                result["ffmpeg_path"] = found
        except Exception:
            pass

    return result


class SilenceAnalyzer:
    def detect_silence(
        self,
        video_path: str,
        min_silence_sec: float = 1.0,
        max_silence_sec: float = 3.5,
        silence_thresh_dbfs: float = -50.0,
    ) -> List[Dict]:
        """
        Detect silence segments in a video file.
        Returns [{"start_time": float, "end_time": float, "label": ""}, ...]
        """
        # ── Step 1: Python 3.13 compatibility — restore audioop ─────────────
        #    audioop was removed from the stdlib in Python 3.13.
        #    pydub 0.25.1 imports it at the top level, so the whole package
        #    fails to import unless audioop-lts is installed as a backport.
        if sys.version_info >= (3, 13):
            try:
                import audioop  # noqa: F401 — succeeds if audioop-lts is installed
            except ModuleNotFoundError:
                raise RuntimeError(
                    "Python 3.13 removed the built-in 'audioop' module that pydub needs.\n\n"
                    "Fix — run this once in the same terminal you use to launch the app:\n\n"
                    "    pip install audioop-lts\n\n"
                    f"(Python: {sys.executable})"
                )

        # ── Step 2: import pydub ─────────────────────────────────────────────
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_silence as pydub_detect
        except ImportError as e:
            raise RuntimeError(
                f"pydub is not importable: {e}\n"
                f"Run: pip install pydub\n"
                f"(Python: {sys.executable})"
            ) from e

        # ── Step 3: verify ffmpeg is reachable before calling pydub ──────────
        ffmpeg_ok = False
        for exe in ("ffmpeg", "ffmpeg.exe"):
            try:
                r = subprocess.run(
                    [exe, "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
                if r.returncode == 0:
                    ffmpeg_ok = True
                    break
            except (FileNotFoundError, OSError):
                continue

        if not ffmpeg_ok:
            raise RuntimeError(
                "ffmpeg is not found on your PATH.\n\n"
                "Fix options:\n"
                "  1. Install via winget:  winget install ffmpeg\n"
                "  2. Download from https://ffmpeg.org/download.html\n"
                "     and add the 'bin' folder to your system PATH.\n\n"
                f"Current PATH:\n{os.environ.get('PATH', '(empty)')}"
            )

        # ── Step 4: decode audio via pydub/ffmpeg ────────────────────────────
        try:
            audio = AudioSegment.from_file(video_path, format="mp4")
        except Exception as e:
            err = str(e)
            # Pydub wraps ffmpeg errors in CouldntDecodeError or generic Exception
            if (
                "ffmpeg" in err.lower()
                or "couldn" in err.lower()
                or "decode" in err.lower()
            ):
                raise RuntimeError(
                    f"ffmpeg failed to decode the audio track.\n\n"
                    f"Detail: {err}\n\n"
                    'Try: ffmpeg -i "your_video.mp4" -vn test_audio.wav\n'
                    "If that also fails the video may have no audio track."
                ) from e
            raise RuntimeError(f"Could not read audio from video:\n{err}") from e

        # ── Step 5: run silence detection ─────────────────────────────────────
        min_silence_ms = int(min_silence_sec * 1000)
        max_silence_ms = int(max_silence_sec * 1000)

        try:
            raw_silences = pydub_detect(
                audio,
                min_silence_len=max(min_silence_ms, 100),
                silence_thresh=silence_thresh_dbfs,
                seek_step=10,
            )
        except Exception as e:
            raise RuntimeError(f"Silence detection failed:\n{e}") from e

        segments = []
        for start_ms, end_ms in raw_silences:
            duration_ms = end_ms - start_ms
            if duration_ms < min_silence_ms:
                continue
            if duration_ms > max_silence_ms:
                continue
            segments.append(
                {
                    "start_time": start_ms / 1000.0,
                    "end_time": end_ms / 1000.0,
                    "label": "",
                }
            )

        return segments
