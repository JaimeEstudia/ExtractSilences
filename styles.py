"""
UI Styles, Colors, and Fonts for Silence Detector
Dark industrial theme — precise and utilitarian.
"""

import tkinter as tk
from tkinter import ttk

COLORS = {
    "bg":           "#0f1117",
    "topbar":       "#080a0f",
    "sidebar":      "#13161e",
    "panel":        "#13161e",
    "list_bg":      "#0f1117",
    "entry_bg":     "#1c2030",
    "border":       "#2a2f3e",
    "divider":      "#1e2330",

    "fg":           "#e2e8f0",
    "muted":        "#566070",
    "label_fg":     "#8892a0",

    "accent":       "#00d4aa",
    "accent_hover": "#00efc0",
    "accent_dim":   "#003d30",

    "silence_bar":  "#ff4d6d",
    "silence_hl":   "#ff8fa3",
    "playhead":     "#ffe066",
    "timeline_bg":  "#1a1e2a",

    "danger":       "#ff4d6d",
    "danger_bg":    "#1a0a0e",

    "seg_even":     "#161b26",
    "seg_odd":      "#0f1117",
    "seg_active":   "#002d24",
    "seg_hover":    "#1c2030",
}

FONTS = {
    "title":   ("Consolas", 13, "bold"),
    "label":   ("Consolas", 9, "bold"),
    "button":  ("Consolas", 10, "bold"),
    "body":    ("Consolas", 10),
    "small":   ("Consolas", 9),
    "mono":    ("Consolas", 10),
    "time":    ("Consolas", 11, "bold"),
}


def apply_styles(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(
        "TProgressbar",
        troughcolor=COLORS["entry_bg"],
        background=COLORS["accent"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["accent"],
        darkcolor=COLORS["accent"],
    )

    style.configure(
        "TScrollbar",
        troughcolor=COLORS["bg"],
        background=COLORS["border"],
        bordercolor=COLORS["bg"],
        arrowcolor=COLORS["muted"],
    )
