"""
VideoPlayer widget — Tkinter canvas-based player using OpenCV + pygame audio.

Bug fixes vs v1:
  1. CRASH FIX  — All cv2.VideoCapture calls now happen exclusively on the
                  playback thread via a seek-request queue.  The main thread
                  never touches _cap directly, eliminating the FFmpeg
                  pthread_frame async-lock race condition.
  2. AUDIO FIX  — pygame.mixer is used to play the video audio track
                  (extracted once to a temp WAV via ffmpeg on load).
                  Playback, pause, stop, and seek are all synchronized.
"""

import tkinter as tk
import threading
import queue
import time
import os
import tempfile
import subprocess
from typing import List, Dict, Callable, Optional

from styles import COLORS, FONTS

try:
    import cv2
    from PIL import Image, ImageTk
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class _Cmd:
    PLAY  = "play"
    PAUSE = "pause"
    STOP  = "stop"
    SEEK  = "seek"
    LOAD  = "load"
    QUIT  = "quit"


class VideoPlayer(tk.Frame):
    TIMELINE_H = 36
    CTRL_H = 48

    def __init__(self, parent, on_position_change: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=COLORS["bg"], **kwargs)
        self.on_position_change = on_position_change

        self._duration: float = 0.0
        self._current_sec: float = 0.0
        self._playing: bool = False
        self._silence_segments: List[Dict] = []
        self._highlighted_segment: Optional[Dict] = None
        self._last_photo = None
        self._audio_path: Optional[str] = None
        self._dragging_timeline = False

        # Command queue: main thread -> playback thread
        self._cmd_q: queue.Queue = queue.Queue()

        self._build()

        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.pre_init(44100, -16, 2, 1024)
                pygame.mixer.init()
            except Exception:
                pass

        self._pb_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._pb_thread.start()

        self.bind("<Destroy>", self._on_destroy)

    # ------------------------------------------------------------------ build

    def _build(self):
        self.canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: None)

        self.timeline = tk.Canvas(
            self, bg=COLORS["timeline_bg"],
            height=self.TIMELINE_H, highlightthickness=0, cursor="hand2"
        )
        self.timeline.pack(fill="x")
        self.timeline.bind("<Button-1>",        self._on_timeline_click)
        self.timeline.bind("<B1-Motion>",       self._on_timeline_drag)
        self.timeline.bind("<ButtonRelease-1>", self._on_timeline_release)

        ctrl = tk.Frame(self, bg=COLORS["topbar"], height=self.CTRL_H)
        ctrl.pack(fill="x")
        ctrl.pack_propagate(False)
        self._build_controls(ctrl)

        self._placeholder = self.canvas.create_text(
            400, 300,
            text="No video loaded\nSelect a video from the library",
            fill=COLORS["muted"], font=FONTS["body"], justify="center"
        )

    def _build_controls(self, parent):
        self.play_btn = tk.Button(
            parent, text="▶",
            bg=COLORS["topbar"], fg=COLORS["accent"],
            font=("Consolas", 16), relief="flat", cursor="hand2",
            activebackground=COLORS["topbar"], activeforeground=COLORS["accent_hover"],
            command=self._toggle_play, width=3,
        )
        self.play_btn.pack(side="left", padx=(16, 4), pady=8)

        tk.Button(
            parent, text="⏹",
            bg=COLORS["topbar"], fg=COLORS["muted"],
            font=("Consolas", 14), relief="flat", cursor="hand2",
            activebackground=COLORS["topbar"], activeforeground=COLORS["fg"],
            command=self.stop, width=3,
        ).pack(side="left", padx=4, pady=8)

        self.time_var = tk.StringVar(value="00:00 / 00:00")
        tk.Label(parent, textvariable=self.time_var,
                 bg=COLORS["topbar"], fg=COLORS["fg"], font=FONTS["time"]
                 ).pack(side="left", padx=16)

        self.seg_info_var = tk.StringVar(value="")
        tk.Label(parent, textvariable=self.seg_info_var,
                 bg=COLORS["topbar"], fg=COLORS["silence_hl"], font=FONTS["small"]
                 ).pack(side="left", padx=8)

        self._audio_icon_var = tk.StringVar(value="🔇")
        tk.Label(parent, textvariable=self._audio_icon_var,
                 bg=COLORS["topbar"], fg=COLORS["muted"], font=("Consolas", 13)
                 ).pack(side="right", padx=16)

    # ------------------------------------------------------------------ public

    def load(self, path: str):
        self._stop_audio()
        self._cmd_q.put((_Cmd.STOP, None))
        threading.Thread(target=self._extract_audio, args=(path,), daemon=True).start()
        self._cmd_q.put((_Cmd.LOAD, path))
        self.canvas.delete(self._placeholder)
        self._playing = False
        self.play_btn.config(text="▶")

    def stop(self):
        self._stop_audio()
        self._playing = False
        self._cmd_q.put((_Cmd.STOP, None))
        self.play_btn.config(text="▶")

    def seek_to(self, seconds: float):
        seconds = max(0.0, min(seconds, self._duration))
        self._seek_audio(seconds)
        self._cmd_q.put((_Cmd.SEEK, seconds))

    def set_silence_segments(self, segments: List[Dict]):
        self._silence_segments = segments
        self._highlighted_segment = None
        self._draw_timeline()

    def highlight_segment(self, segment: Dict):
        self._highlighted_segment = segment
        self._draw_timeline()
        dur = segment["end_time"] - segment["start_time"]
        label = segment.get("label") or f"Segment #{segment.get('id','?')}"
        self.seg_info_var.set(f"▶ {label}  [{dur:.1f}s]")

    # ------------------------------------------------------------------ audio

    def _extract_audio(self, video_path: str):
        if self._audio_path and os.path.exists(self._audio_path):
            try:
                os.unlink(self._audio_path)
            except OSError:
                pass
        self._audio_path = None

        if not PYGAME_AVAILABLE:
            self.after(0, lambda: self._audio_icon_var.set("🔇"))
            return

        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            result = subprocess.run(
                ["ffmpeg", "-y", "-i", video_path,
                 "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                 tmp_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            if result.returncode == 0 and os.path.getsize(tmp_path) > 0:
                self._audio_path = tmp_path
                self.after(0, lambda: self._audio_icon_var.set("🔊"))
            else:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                self.after(0, lambda: self._audio_icon_var.set("🔇"))
        except Exception:
            self.after(0, lambda: self._audio_icon_var.set("🔇"))

    def _play_audio(self, from_sec: float = 0.0):
        if not PYGAME_AVAILABLE or not self._audio_path:
            return
        try:
            pygame.mixer.music.load(self._audio_path)
            pygame.mixer.music.play(start=from_sec)
        except Exception:
            pass

    def _pause_audio(self):
        if not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass

    def _resume_audio(self):
        if not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.music.unpause()
        except Exception:
            pass

    def _stop_audio(self):
        if not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def _seek_audio(self, seconds: float):
        if not PYGAME_AVAILABLE or not self._audio_path:
            return
        try:
            if self._playing:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(self._audio_path)
                pygame.mixer.music.play(start=seconds)
        except Exception:
            pass

    # ------------------------------------------------------------------ playback thread
    # CRITICAL: self._cap (cv2.VideoCapture) is ONLY accessed inside this
    # method. The main thread sends commands via self._cmd_q. This eliminates
    # the FFmpeg pthread_frame async-lock assertion failure that occurs when
    # cap.set() and cap.read() are called concurrently from different threads.

    def _playback_loop(self):
        cap = None
        fps = 30.0
        playing = False
        current_frame = 0
        total_frames = 0
        video_path = None

        while True:
            block = (1.0 / fps) if playing else 0.05
            try:
                cmd, data = self._cmd_q.get(timeout=block)
            except queue.Empty:
                cmd, data = None, None

            # Drain all pending commands first
            while cmd is not None:
                if cmd == _Cmd.QUIT:
                    if cap:
                        cap.release()
                    return

                elif cmd == _Cmd.LOAD:
                    if cap:
                        cap.release()
                        cap = None
                    video_path = data
                    # CAP_PROP_BUFFERSIZE=1 disables read-ahead buffering,
                    # which is what triggers the async_lock assertion on seek.
                    cap = cv2.VideoCapture(video_path)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if cap.isOpened():
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                        duration = total_frames / fps
                        current_frame = 0
                        playing = False
                        self.after(0, lambda d=duration: self._on_loaded(d))
                        ret, frame = cap.read()
                        if ret:
                            current_frame = 1
                            self.after(0, lambda f=frame: self._on_frame(f, 0.0))
                    else:
                        cap = None
                        self.after(0, lambda: self._show_placeholder("Cannot open video."))

                elif cmd == _Cmd.PLAY:
                    playing = True

                elif cmd == _Cmd.PAUSE:
                    playing = False

                elif cmd == _Cmd.STOP:
                    playing = False
                    current_frame = 0
                    if cap and cap.isOpened():
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()
                        if ret:
                            current_frame = 1
                            self.after(0, lambda f=frame: self._on_frame(f, 0.0))

                elif cmd == _Cmd.SEEK:
                    if cap and cap.isOpened():
                        target_sec = float(data)
                        fps_local = fps if fps > 0 else 30.0
                        target_frame = max(0, min(int(target_sec * fps_local), total_frames - 1))
                        # Re-open the capture to guarantee a clean seek context.
                        # This is the most reliable way to avoid the async_lock
                        # assertion: a fresh VideoCapture has no in-flight decode state.
                        was_playing = playing
                        playing = False
                        cap.release()
                        cap = cv2.VideoCapture(video_path)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                        ret, frame = cap.read()
                        if ret:
                            current_frame = target_frame + 1
                            seek_sec = target_frame / fps_local
                            self.after(0, lambda f=frame, s=seek_sec: self._on_frame(f, s))
                        playing = was_playing

                try:
                    cmd, data = self._cmd_q.get_nowait()
                except queue.Empty:
                    cmd, data = None, None

            # Render next frame during playback
            if playing and cap and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    playing = False
                    self.after(0, lambda: self.play_btn.config(text="▶"))
                    self.after(0, lambda: setattr(self, '_playing', False))
                else:
                    current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                    sec = current_frame / fps
                    self.after(0, lambda f=frame, s=sec: self._on_frame(f, s))

    # ------------------------------------------------------------------ callbacks (main thread)

    def _on_loaded(self, duration: float):
        self._duration = duration
        self._current_sec = 0.0
        self._highlighted_segment = None
        self._update_time_display(0.0)
        self._draw_timeline()

    def _on_frame(self, frame, sec: float):
        self._current_sec = sec
        self._display_frame(frame)
        self._update_time_display(sec)
        self._draw_timeline(playhead_sec=sec)
        if self.on_position_change:
            self.on_position_change(sec)
        for seg in self._silence_segments:
            if seg["start_time"] <= sec <= seg["end_time"]:
                label = seg.get("label") or f"Silence #{seg.get('id','?')}"
                self.seg_info_var.set(f"🔇 {label}")
                return
        self.seg_info_var.set("")

    # ------------------------------------------------------------------ frame display

    def _display_frame(self, frame):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 2 or h < 2:
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fh, fw = frame_rgb.shape[:2]
        scale = min(w / fw, h / fh)
        nw, nh = int(fw * scale), int(fh * scale)
        resized = cv2.resize(frame_rgb, (nw, nh))
        img = Image.fromarray(resized)
        photo = ImageTk.PhotoImage(img)
        self._last_photo = photo
        self.canvas.delete("frame")
        x = (w - nw) // 2
        y = (h - nh) // 2
        self.canvas.create_image(x, y, anchor="nw", image=photo, tags="frame")

    def _show_placeholder(self, msg: str):
        self.canvas.delete("frame")
        self._placeholder = self.canvas.create_text(
            400, 200, text=msg,
            fill=COLORS["muted"], font=FONTS["body"], justify="center"
        )

    # ------------------------------------------------------------------ controls

    def _toggle_play(self):
        if self._duration <= 0:
            return
        if self._playing:
            self._playing = False
            self.play_btn.config(text="▶")
            self._pause_audio()
            self._cmd_q.put((_Cmd.PAUSE, None))
        else:
            self._playing = True
            self.play_btn.config(text="⏸")
            self._cmd_q.put((_Cmd.PLAY, None))
            if PYGAME_AVAILABLE and self._audio_path:
                try:
                    if pygame.mixer.music.get_busy():
                        self._resume_audio()
                    else:
                        self._play_audio(from_sec=self._current_sec)
                except Exception:
                    pass

    # ------------------------------------------------------------------ timeline

    def _draw_timeline(self, playhead_sec: Optional[float] = None):
        tl = self.timeline
        tl.delete("all")
        w = tl.winfo_width()
        h = self.TIMELINE_H
        if w < 2:
            return

        tl.create_rectangle(0, 0, w, h, fill=COLORS["timeline_bg"], outline="")
        mid = h // 2
        tl.create_rectangle(0, mid - 2, w, mid + 2, fill=COLORS["border"], outline="")

        if self._duration <= 0:
            return

        for seg in self._silence_segments:
            x1 = int(seg["start_time"] / self._duration * w)
            x2 = int(seg["end_time"]   / self._duration * w)
            x2 = max(x2, x1 + 2)
            is_hl = (
                self._highlighted_segment is not None
                and self._highlighted_segment.get("id") == seg.get("id")
            )
            color = COLORS["silence_hl"] if is_hl else COLORS["silence_bar"]
            bar_h = 18 if is_hl else 12
            tl.create_rectangle(x1, mid - bar_h // 2, x2, mid + bar_h // 2,
                                 fill=color, outline="")

        sec = playhead_sec if playhead_sec is not None else self._current_sec
        px = int(sec / self._duration * w)
        tl.create_line(px, 0, px, h, fill=COLORS["playhead"], width=2)
        tl.create_oval(px - 5, mid - 5, px + 5, mid + 5,
                       fill=COLORS["playhead"], outline="")

    def _timeline_x_to_sec(self, x: int) -> float:
        w = self.timeline.winfo_width()
        if w < 2 or self._duration <= 0:
            return 0.0
        return max(0.0, min(float(x) / w * self._duration, self._duration))

    def _on_timeline_click(self, event):
        self._dragging_timeline = False
        self.seek_to(self._timeline_x_to_sec(event.x))

    def _on_timeline_drag(self, event):
        self._dragging_timeline = True
        sec = self._timeline_x_to_sec(event.x)
        self._update_time_display(sec)
        self._draw_timeline(playhead_sec=sec)

    def _on_timeline_release(self, event):
        if self._dragging_timeline:
            self.seek_to(self._timeline_x_to_sec(event.x))
        self._dragging_timeline = False

    # ------------------------------------------------------------------ helpers

    def _update_time_display(self, sec: float):
        self.time_var.set(f"{self._fmt(sec)} / {self._fmt(self._duration)}")

    @staticmethod
    def _fmt(sec: float) -> str:
        m, s = divmod(int(sec), 60)
        return f"{m:02d}:{s:02d}"

    def _on_destroy(self, event):
        self._cmd_q.put((_Cmd.QUIT, None))
        self._stop_audio()
        if self._audio_path and os.path.exists(self._audio_path):
            try:
                os.unlink(self._audio_path)
            except OSError:
                pass
