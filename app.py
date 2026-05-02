"""
Video Silence Detector - Main Application
Tkinter GUI for uploading MP4 videos and detecting silence segments.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys

from database import Database
from silence_analyzer import SilenceAnalyzer, check_dependencies
from video_player import VideoPlayer
from segments_panel import SegmentsPanel
from styles import apply_styles, COLORS, FONTS


class SilenceDetectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Silence Detector")
        self.geometry("1400x860")
        self.minsize(1100, 700)
        self.configure(bg=COLORS["bg"])

        self.db = Database()
        self.analyzer = SilenceAnalyzer()
        self.current_video_id = None
        self.current_video_path = None

        apply_styles(self)
        self._build_ui()
        self._load_video_list()

    # ─── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        topbar = tk.Frame(self, bg=COLORS["topbar"], height=52)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(
            topbar,
            text="  🎬  SILENCE DETECTOR",
            bg=COLORS["topbar"],
            fg=COLORS["accent"],
            font=FONTS["title"],
        ).pack(side="left", padx=20, pady=12)

        tk.Label(
            topbar,
            text="Detect · Label · Export",
            bg=COLORS["topbar"],
            fg=COLORS["muted"],
            font=FONTS["small"],
        ).pack(side="left", padx=4, pady=12)

        # ── Main layout: left sidebar + center content ────────────────────
        main = tk.Frame(self, bg=COLORS["bg"])
        main.pack(fill="both", expand=True)

        # Left sidebar
        self.sidebar = tk.Frame(main, bg=COLORS["sidebar"], width=260)
        self.sidebar.pack(fill="y", side="left")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        # Right: player + segments
        right = tk.Frame(main, bg=COLORS["bg"])
        right.pack(fill="both", expand=True, side="left")

        # Player area (top-right)
        player_frame = tk.Frame(right, bg=COLORS["bg"])
        player_frame.pack(fill="both", expand=True, side="top")

        self.video_player = VideoPlayer(player_frame, on_position_change=self._on_player_position_change)
        self.video_player.pack(fill="both", expand=True)

        # Bottom strip: segments + params
        bottom = tk.Frame(right, bg=COLORS["panel"], height=300)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self._build_bottom_panel(bottom)

    def _build_sidebar(self):
        sb = self.sidebar

        # Header
        hdr = tk.Frame(sb, bg=COLORS["sidebar"])
        hdr.pack(fill="x", padx=14, pady=(18, 8))
        tk.Label(hdr, text="VIDEO LIBRARY", bg=COLORS["sidebar"],
                 fg=COLORS["muted"], font=FONTS["label"]).pack(side="left")

        # Upload button
        upload_btn = tk.Button(
            sb, text="＋  Upload MP4",
            bg=COLORS["accent"], fg=COLORS["bg"],
            font=FONTS["button"], relief="flat", cursor="hand2",
            activebackground=COLORS["accent_hover"], activeforeground=COLORS["bg"],
            command=self._upload_video, padx=10, pady=8,
        )
        upload_btn.pack(fill="x", padx=14, pady=(0, 12))

        # Video list
        list_frame = tk.Frame(sb, bg=COLORS["sidebar"])
        list_frame.pack(fill="both", expand=True, padx=6)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical",
                                 bg=COLORS["sidebar"], troughcolor=COLORS["sidebar"])
        self.video_listbox = tk.Listbox(
            list_frame,
            bg=COLORS["list_bg"],
            fg=COLORS["fg"],
            font=FONTS["body"],
            selectbackground=COLORS["accent"],
            selectforeground=COLORS["bg"],
            relief="flat", bd=0,
            highlightthickness=0,
            activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.video_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.video_listbox.pack(fill="both", expand=True)
        self.video_listbox.bind("<<ListboxSelect>>", self._on_video_select)

        # Delete button
        tk.Button(
            sb, text="🗑  Remove Selected",
            bg=COLORS["danger_bg"], fg=COLORS["danger"],
            font=FONTS["small"], relief="flat", cursor="hand2",
            activebackground=COLORS["danger_bg"], activeforeground=COLORS["danger"],
            command=self._remove_video, pady=6,
        ).pack(fill="x", padx=14, pady=(8, 14))

    def _build_bottom_panel(self, parent):
        # Left: segments panel
        seg_frame = tk.Frame(parent, bg=COLORS["panel"])
        seg_frame.pack(fill="both", expand=True, side="left")

        self.segments_panel = SegmentsPanel(
            seg_frame,
            on_segment_click=self._on_segment_click,
            on_label_change=self._on_label_change,
            on_export=self._export_csv,
        )
        self.segments_panel.pack(fill="both", expand=True)

        # Divider
        tk.Frame(parent, bg=COLORS["divider"], width=1).pack(fill="y", side="left")

        # Right: parameters
        params_frame = tk.Frame(parent, bg=COLORS["panel"], width=290)
        params_frame.pack(fill="y", side="right")
        params_frame.pack_propagate(False)
        self._build_params_panel(params_frame)

    def _build_params_panel(self, parent):
        tk.Label(parent, text="DETECTION PARAMETERS", bg=COLORS["panel"],
                 fg=COLORS["muted"], font=FONTS["label"]).pack(anchor="w", padx=18, pady=(12, 6))

        fields = [
            ("Min silence duration (s)", "min_silence", "1.0"),
            ("Max silence duration (s)", "max_silence", "60.0"),
            ("Noise threshold (dBFS)", "noise_thresh", "-40"),
        ]
        self.param_vars = {}
        for label, key, default in fields:
            row = tk.Frame(parent, bg=COLORS["panel"])
            row.pack(fill="x", padx=18, pady=3)
            tk.Label(row, text=label, bg=COLORS["panel"],
                     fg=COLORS["fg"], font=FONTS["body"]).pack(anchor="w")
            var = tk.StringVar(value=default)
            self.param_vars[key] = var
            entry = tk.Entry(
                row, textvariable=var,
                bg=COLORS["entry_bg"], fg=COLORS["fg"],
                font=FONTS["body"], relief="flat",
                insertbackground=COLORS["accent"],
                highlightthickness=1,
                highlightcolor=COLORS["accent"],
                highlightbackground=COLORS["border"],
            )
            entry.pack(fill="x", ipady=5, pady=(2, 0))

        # Analyze button — packed before status so it's never pushed off screen
        self.analyze_btn = tk.Button(
            parent, text="▶  Analyze Silence",
            bg=COLORS["accent"], fg=COLORS["bg"],
            font=FONTS["button"], relief="flat", cursor="hand2",
            activebackground=COLORS["accent_hover"],
            activeforeground=COLORS["bg"],
            command=self._run_analysis, pady=8,
        )
        self.analyze_btn.pack(fill="x", padx=18, pady=(10, 4))

        # Progress bar
        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(fill="x", padx=18, pady=(0, 4))

        # Diagnose button
        tk.Button(
            parent, text="🔍  Diagnose Dependencies",
            bg=COLORS["entry_bg"], fg=COLORS["muted"],
            font=FONTS["small"], relief="flat", cursor="hand2",
            activebackground=COLORS["border"], activeforeground=COLORS["fg"],
            command=self._run_diagnostics, pady=5,
        ).pack(fill="x", padx=18, pady=(0, 6))

        # Status label
        self.status_var = tk.StringVar(value="No video loaded.")
        tk.Label(parent, textvariable=self.status_var, bg=COLORS["panel"],
                 fg=COLORS["muted"], font=FONTS["small"],
                 wraplength=250, justify="left").pack(anchor="w", padx=18, pady=(0, 6))

    # ─── Video Library ───────────────────────────────────────────────────────

    def _load_video_list(self):
        self.video_listbox.delete(0, "end")
        self._video_ids = []
        for vid in self.db.get_all_videos():
            name = os.path.basename(vid["path"])
            self.video_listbox.insert("end", f"  {name}")
            self._video_ids.append(vid["id"])

    def _upload_video(self):
        path = filedialog.askopenfilename(
            title="Select MP4 video",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        if not path:
            return
        vid_id = self.db.add_video(path)
        self._load_video_list()
        # Select the newly added video
        idx = self._video_ids.index(vid_id)
        self.video_listbox.selection_clear(0, "end")
        self.video_listbox.selection_set(idx)
        self._load_video(vid_id, path)

    def _remove_video(self):
        sel = self.video_listbox.curselection()
        if not sel:
            return
        vid_id = self._video_ids[sel[0]]
        if messagebox.askyesno("Remove", "Remove this video from the library?"):
            self.db.remove_video(vid_id)
            if self.current_video_id == vid_id:
                self.video_player.stop()
                self.segments_panel.clear()
                self.current_video_id = None
                self.current_video_path = None
                self.status_var.set("No video loaded.")
            self._load_video_list()

    def _on_video_select(self, event):
        sel = self.video_listbox.curselection()
        if not sel:
            return
        vid_id = self._video_ids[sel[0]]
        video = self.db.get_video(vid_id)
        if video:
            self._load_video(vid_id, video["path"])

    def _load_video(self, vid_id, path):
        if not os.path.exists(path):
            messagebox.showerror("File Not Found", f"Cannot find:\n{path}")
            return
        self.current_video_id = vid_id
        self.current_video_path = path
        self.video_player.load(path)
        self.status_var.set(f"Loaded: {os.path.basename(path)}")
        # Load existing segments if any
        segments = self.db.get_segments(vid_id)
        self.segments_panel.load_segments(segments)
        self.video_player.set_silence_segments(segments)

    # ─── Analysis ────────────────────────────────────────────────────────────

    def _get_params(self):
        try:
            min_s = float(self.param_vars["min_silence"].get())
            max_s = float(self.param_vars["max_silence"].get())
            thresh = float(self.param_vars["noise_thresh"].get())
            if min_s < 0 or max_s < min_s:
                raise ValueError
            if thresh > 0:
                raise ValueError("Threshold should be negative dBFS")
            return min_s, max_s, thresh
        except ValueError as e:
            messagebox.showerror("Invalid Parameters",
                                 "Please check:\n• Min/Max duration (positive, min ≤ max)\n• Threshold (negative number, e.g. -40)")
            return None

    def _run_analysis(self):
        if not self.current_video_path:
            messagebox.showwarning("No Video", "Please select a video first.")
            return
        params = self._get_params()
        if params is None:
            return
        min_s, max_s, thresh = params
        self.analyze_btn.config(state="disabled")
        self.progress.start(12)
        self.status_var.set("Analyzing audio…")

        def worker():
            try:
                segments = self.analyzer.detect_silence(
                    self.current_video_path, min_s, max_s, thresh
                )
                self.db.save_segments(self.current_video_id, segments)
                db_segments = self.db.get_segments(self.current_video_id)
                self.after(0, lambda: self._analysis_done(db_segments))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._analysis_error(m))

        threading.Thread(target=worker, daemon=True).start()

    def _analysis_done(self, segments):
        self.progress.stop()
        self.analyze_btn.config(state="normal")
        self.segments_panel.load_segments(segments)
        self.video_player.set_silence_segments(segments)
        self.status_var.set(f"Found {len(segments)} silence segment(s).")

    def _analysis_error(self, msg):
        self.progress.stop()
        self.analyze_btn.config(state="normal")
        self.status_var.set("Analysis failed.")
        messagebox.showerror("Analysis Error", f"Could not analyze video:\n{msg}")

    def _run_diagnostics(self):
        """Run dependency checks and show results in a detailed popup."""
        from tkinter import scrolledtext
        diag = check_dependencies()

        win = tk.Toplevel(self)
        win.title("Dependency Diagnostics")
        win.geometry("600x420")
        win.configure(bg=COLORS["bg"])
        win.resizable(True, True)

        tk.Label(win, text="DEPENDENCY DIAGNOSTICS", bg=COLORS["bg"],
                 fg=COLORS["accent"], font=FONTS["label"]).pack(anchor="w", padx=20, pady=(16, 6))

        txt = scrolledtext.ScrolledText(
            win, bg=COLORS["entry_bg"], fg=COLORS["fg"],
            font=("Consolas", 10), relief="flat",
            insertbackground=COLORS["accent"],
        )
        txt.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        import sys, os
        lines = []
        lines.append(f"Python executable : {sys.executable}")
        lines.append(f"Python version    : {sys.version.split()[0]}")
        lines.append("")
        import sys as _sys
        if _sys.version_info >= (3, 13):
            audioop_status = 'YES' if diag.get('audioop') else 'NO  <-- pip install audioop-lts'
        else:
            audioop_status = 'N/A (only needed on Python 3.13+)'
        lines.append(f"pydub installed   : {'YES' if diag['pydub'] else 'NO  <-- pip install pydub'}")
        lines.append(f"audioop-lts       : {audioop_status}")
        lines.append(f"ffmpeg on PATH    : {'YES  (' + diag['ffmpeg_path'] + ')' if diag['ffmpeg'] else 'NO  <-- install ffmpeg and add to PATH'}")
        lines.append(f"ffprobe on PATH   : {'YES' if diag['ffprobe'] else 'NO  (optional but recommended)'}")
        if diag["error"]:
            lines.append("")
            lines.append(f"Error detail      : {diag['error']}")

        lines.append("")
        lines.append("── PATH entries ──────────────────────────────────────────")
        for p in os.environ.get("PATH", "").split(os.pathsep):
            lines.append(f"  {p}")

        txt.insert("end", "\n".join(lines))
        txt.config(state="disabled")

        # Copy button
        def copy_all():
            win.clipboard_clear()
            win.clipboard_append(txt.get("1.0", "end"))
        tk.Button(win, text="📋 Copy to Clipboard",
                  bg=COLORS["accent_dim"], fg=COLORS["accent"],
                  font=FONTS["small"], relief="flat", cursor="hand2",
                  command=copy_all, pady=6).pack(padx=20, pady=(0, 16))

    # ─── Segment interaction ──────────────────────────────────────────────────

    def _on_segment_click(self, segment):
        self.video_player.seek_to(segment["start_time"])
        self.video_player.highlight_segment(segment)

    def _on_label_change(self, segment_id, label):
        self.db.update_segment_label(segment_id, label)

    def _on_player_position_change(self, position_sec):
        self.segments_panel.highlight_active(position_sec)

    # ─── Export ───────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self.current_video_id:
            messagebox.showwarning("No Video", "No video loaded.")
            return
        segments = self.db.get_segments(self.current_video_id)
        if not segments:
            messagebox.showinfo("No Segments", "No silence segments to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"silence_segments_{os.path.splitext(os.path.basename(self.current_video_path))[0]}.csv"
        )
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Label", "Start (s)", "End (s)", "Duration (s)"])
            for i, seg in enumerate(segments, 1):
                writer.writerow([
                    i,
                    seg.get("label", ""),
                    f"{seg['start_time']:.3f}",
                    f"{seg['end_time']:.3f}",
                    f"{seg['end_time'] - seg['start_time']:.3f}",
                ])
        messagebox.showinfo("Exported", f"Saved {len(segments)} segments to:\n{path}")


if __name__ == "__main__":
    app = SilenceDetectorApp()
    app.mainloop()
