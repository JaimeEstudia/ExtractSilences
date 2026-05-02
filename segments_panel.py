"""
Segments panel — shows detected silence segments in a scrollable list.
Supports inline label editing, click-to-seek, and CSV export trigger.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Callable, Optional

from styles import COLORS, FONTS


class SegmentsPanel(tk.Frame):
    ROW_H = 38

    def __init__(
        self,
        parent,
        on_segment_click: Optional[Callable] = None,
        on_label_change: Optional[Callable] = None,
        on_export: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(parent, bg=COLORS["panel"], **kwargs)
        self.on_segment_click = on_segment_click
        self.on_label_change = on_label_change
        self.on_export = on_export

        self._segments: List[Dict] = []
        self._row_frames: List[tk.Frame] = []
        self._active_id: Optional[int] = None

        self._build()

    # ─── Build ───────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=COLORS["panel"])
        hdr.pack(fill="x", padx=14, pady=(10, 4))

        tk.Label(
            hdr, text="SILENCE SEGMENTS",
            bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["label"]
        ).pack(side="left")

        self.count_var = tk.StringVar(value="")
        tk.Label(
            hdr, textvariable=self.count_var,
            bg=COLORS["panel"], fg=COLORS["accent"], font=FONTS["label"]
        ).pack(side="left", padx=8)

        tk.Button(
            hdr, text="⬇ Export CSV",
            bg=COLORS["accent_dim"], fg=COLORS["accent"],
            font=FONTS["small"], relief="flat", cursor="hand2",
            activebackground=COLORS["accent_dim"], activeforeground=COLORS["accent_hover"],
            command=lambda: self.on_export() if self.on_export else None,
            padx=8, pady=3,
        ).pack(side="right")

        # Column headers
        col_hdr = tk.Frame(self, bg=COLORS["border"])
        col_hdr.pack(fill="x", padx=14)
        for text, w in [("#", 30), ("Start", 70), ("End", 70), ("Duration", 75), ("Label", 0)]:
            tk.Label(
                col_hdr, text=text,
                bg=COLORS["border"], fg=COLORS["muted"],
                font=FONTS["small"], width=w // 8 if w else 0, anchor="w"
            ).pack(side="left", padx=(4, 0), pady=3)

        # Scrollable list
        container = tk.Frame(self, bg=COLORS["panel"])
        container.pack(fill="both", expand=True, padx=14, pady=(4, 8))

        scroll = tk.Scrollbar(container, orient="vertical",
                              bg=COLORS["border"], troughcolor=COLORS["panel"])
        self.list_canvas = tk.Canvas(
            container, bg=COLORS["panel"], highlightthickness=0,
            yscrollcommand=scroll.set
        )
        scroll.config(command=self.list_canvas.yview)
        scroll.pack(side="right", fill="y")
        self.list_canvas.pack(side="left", fill="both", expand=True)

        self.rows_frame = tk.Frame(self.list_canvas, bg=COLORS["panel"])
        self._canvas_window = self.list_canvas.create_window(
            (0, 0), window=self.rows_frame, anchor="nw"
        )
        self.rows_frame.bind("<Configure>", self._on_rows_configure)
        self.list_canvas.bind("<Configure>", self._on_canvas_configure)
        self.list_canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Empty label
        self.empty_label = tk.Label(
            self.rows_frame,
            text="No segments detected yet.\nConfigure parameters and click Analyze.",
            bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["small"],
            justify="center"
        )
        self.empty_label.pack(pady=20)

    # ─── Public API ──────────────────────────────────────────────────────────

    def load_segments(self, segments: List[Dict]):
        self._segments = segments
        self._render_rows()

    def clear(self):
        self._segments = []
        self._render_rows()

    def highlight_active(self, position_sec: float):
        active_id = None
        for seg in self._segments:
            if seg["start_time"] <= position_sec <= seg["end_time"]:
                active_id = seg["id"]
                break
        if active_id == self._active_id:
            return
        self._active_id = active_id
        for i, (seg, frame) in enumerate(zip(self._segments, self._row_frames)):
            bg = COLORS["seg_active"] if seg["id"] == active_id else (
                COLORS["seg_even"] if i % 2 == 0 else COLORS["seg_odd"]
            )
            self._recolor_frame(frame, bg)

    # ─── Rendering ───────────────────────────────────────────────────────────

    def _render_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self._row_frames = []

        if not self._segments:
            self.count_var.set("")
            self.empty_label = tk.Label(
                self.rows_frame,
                text="No segments detected yet.\nConfigure parameters and click Analyze.",
                bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["small"],
                justify="center"
            )
            self.empty_label.pack(pady=20)
            return

        self.count_var.set(f"({len(self._segments)})")

        for i, seg in enumerate(self._segments):
            bg = COLORS["seg_even"] if i % 2 == 0 else COLORS["seg_odd"]
            row = tk.Frame(self.rows_frame, bg=bg, cursor="hand2")
            row.pack(fill="x", pady=1)
            self._row_frames.append(row)
            self._build_row(row, seg, i + 1, bg)
            row.bind("<Enter>", lambda e, r=row: r.config(bg=COLORS["seg_hover"]) or
                     [c.config(bg=COLORS["seg_hover"]) for c in r.winfo_children()
                      if not isinstance(c, tk.Entry)])
            row.bind("<Leave>", lambda e, r=row, b=bg: r.config(bg=b) or
                     [c.config(bg=b) for c in r.winfo_children()
                      if not isinstance(c, tk.Entry)])

    def _build_row(self, row: tk.Frame, seg: Dict, idx: int, bg: str):
        dur = seg["end_time"] - seg["start_time"]

        def click(e, s=seg):
            if self.on_segment_click:
                self.on_segment_click(s)

        for widget_args in [
            dict(text=f"{idx:>2}", width=3),
            dict(text=self._fmt(seg["start_time"]), width=7),
            dict(text=self._fmt(seg["end_time"]), width=7),
            dict(text=f"{dur:.1f}s", width=7),
        ]:
            lbl = tk.Label(
                row, bg=bg, fg=COLORS["fg"], font=FONTS["mono"],
                anchor="w", padx=6, pady=6, **widget_args
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", click)

        # Inline label entry
        label_var = tk.StringVar(value=seg.get("label", ""))
        entry = tk.Entry(
            row,
            textvariable=label_var,
            bg=COLORS["entry_bg"], fg=COLORS["fg"],
            font=FONTS["mono"], relief="flat",
            insertbackground=COLORS["accent"],
            highlightthickness=1,
            highlightcolor=COLORS["accent"],
            highlightbackground=COLORS["border"],
        )
        entry.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=4, ipady=3)

        def on_label_commit(e, sid=seg["id"], var=label_var):
            if self.on_label_change:
                self.on_label_change(sid, var.get())
                # Update local segment dict too
                for s in self._segments:
                    if s["id"] == sid:
                        s["label"] = var.get()

        entry.bind("<Return>", on_label_commit)
        entry.bind("<FocusOut>", on_label_commit)

        # Silence icon
        tk.Label(row, text="🔇", bg=bg, font=("Consolas", 11)).pack(side="right", padx=6)

    def _recolor_frame(self, frame: tk.Frame, bg: str):
        frame.config(bg=bg)
        for child in frame.winfo_children():
            if not isinstance(child, tk.Entry):
                try:
                    child.config(bg=bg)
                except tk.TclError:
                    pass

    # ─── Layout helpers ───────────────────────────────────────────────────────

    def _on_rows_configure(self, event):
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.list_canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    @staticmethod
    def _fmt(sec: float) -> str:
        m, s = divmod(int(sec), 60)
        ms = int((sec - int(sec)) * 10)
        return f"{m:02d}:{s:02d}.{ms}"
