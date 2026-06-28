#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LYRICA Album Visualizer v1.3
Lyrics Computational Analyzer - visualization helper

Purpose:
- Open an album output folder
- Open an artist/albums root folder
- Search recursively for *_analysis.txt or analysis.txt
- Parse song-level and album-level metrics from LYRICA text reports
- Visualize songs grouped by album or compare integrated album scores
- Visualize the album without changing the main LYRICA analyzer

Run:
    python3 lyrica_album_visualizer.py

Dependencies:
    pip install matplotlib
"""

import re
import csv
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import matplotlib
matplotlib.use("TkAgg")

# Force opaque light figures even if the user has a dark/transparent matplotlibrc.
# This fixes black/empty-looking PNG exports under dark Linux themes.
matplotlib.rcParams["figure.facecolor"] = "white"
matplotlib.rcParams["axes.facecolor"] = "white"
matplotlib.rcParams["savefig.facecolor"] = "white"
matplotlib.rcParams["savefig.edgecolor"] = "white"
matplotlib.rcParams["savefig.transparent"] = False
matplotlib.rcParams["text.color"] = "black"
matplotlib.rcParams["axes.labelcolor"] = "black"
matplotlib.rcParams["axes.edgecolor"] = "black"
matplotlib.rcParams["xtick.color"] = "black"
matplotlib.rcParams["ytick.color"] = "black"

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib import colors as mcolors


# ============================================================
# COLORS / EXPORT SAFETY
# ============================================================

def clamp01(x):
    return max(0.0, min(1.0, float(x)))


def mix_with(color, target=(1, 1, 1, 1), amount=0.25):
    """Blend a Matplotlib color with target color."""
    c = mcolors.to_rgba(color)
    t = mcolors.to_rgba(target)
    a = clamp01(amount)
    return tuple((1.0 - a) * c[i] + a * t[i] for i in range(4))


def lighten(color, amount=0.30):
    return mix_with(color, (1, 1, 1, 1), amount)


def darken(color, amount=0.18):
    return mix_with(color, (0, 0, 0, 1), amount)


def alternating_colors(base_colors, start_dark=True):
    """Return alternating darker/lighter variants while preserving album hue.

    Used only for album-level bars, where the album colors are already readable.
    Song-level long bars use a stronger violet/green row palette below.
    """
    out = []
    for i, c in enumerate(base_colors):
        use_dark = (i % 2 == 0) if start_dark else (i % 2 == 1)
        out.append(darken(c, 0.12) if use_dark else lighten(c, 0.24))
    return out


def readable_row_colors(n, alpha=0.86):
    """High-readability alternating colors for long horizontal song bars.

    The colors are intentionally different hues, not just lighter/darker
    variants of the same album color.  This makes each long row easy to
    follow from the y-label to the end of the bar.

    Odd/even rows:
        lavender-violet / mint-green
    """
    violet = mcolors.to_rgba("#c4b5fd")  # readable lavender/violet
    green = mcolors.to_rgba("#86efac")   # readable mint green
    out = []
    for i in range(int(n)):
        c = violet if i % 2 == 0 else green
        out.append((c[0], c[1], c[2], float(alpha)))
    return out


def readable_pair_colors(n, alpha1=0.90, alpha2=0.52):
    """Return two alternating palettes for dual horizontal bars."""
    base = readable_row_colors(n, alpha=alpha1)
    pale = []
    for c in base:
        cc = mix_with(c, (1, 1, 1, 1), 0.45)
        pale.append((cc[0], cc[1], cc[2], float(alpha2)))
    return base, pale


def force_opaque_figure(fig):
    """Force a white, non-transparent figure/axes before drawing or saving."""
    fig.patch.set_facecolor("white")
    fig.patch.set_alpha(1.0)
    for ax in fig.axes:
        ax.set_facecolor("white")
        ax.patch.set_alpha(1.0)
        ax.title.set_color("black")
        ax.xaxis.label.set_color("black")
        ax.yaxis.label.set_color("black")
        ax.tick_params(colors="black")
        for spine in ax.spines.values():
            spine.set_color("black")
    return fig


def save_opaque_png(fig, path, dpi=180):
    """Save as real opaque PNG, independent of TkAgg/dark desktop themes."""
    force_opaque_figure(fig)
    FigureCanvasAgg(fig).draw()
    fig.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
        edgecolor="white",
        transparent=False,
    )

    # If Pillow is available, rewrite RGBA/LA/P images to RGB on white.
    # This prevents transparent PNGs from disappearing on black viewers.
    try:
        from PIL import Image
        img = Image.open(path)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            bg.alpha_composite(rgba)
            bg.convert("RGB").save(path)
        elif img.mode != "RGB":
            img.convert("RGB").save(path)
    except Exception:
        pass


# ============================================================
# PARSING
# ============================================================

SONG_RE = re.compile(
    r"(?ms)^SONG:\s*(.+?)\s*\n=+\n(.*?)(?=^\n?={20,}\n\nSONG:|\Z)"
)

FIELD_PATTERNS = {
    "blocks": r"Blocks\s*/\s*paragraphs\s*:\s*([0-9.]+)",
    "lines": r"Lines\s*:\s*([0-9.]+)",
    "words": r"Words\s*:\s*([0-9.]+)",
    "unique_words": r"Unique words\s*:\s*([0-9.]+)",
    "characters": r"Characters\s*:\s*([0-9.]+)",
    "avg_words_per_line": r"Avg words per line\s*:\s*([0-9.]+)",
    "lexical_density": r"Lexical density\s*:\s*([0-9.]+)",
    "repeated_line_mass": r"Repeated line mass\s*:\s*([0-9.]+)",

    "mean_block_shannon": r"Mean block Shannon\s*:\s*([0-9.]+)",
    "min_block_shannon": r"Min block Shannon\s*:\s*([0-9.]+)",
    "max_block_shannon": r"Max block Shannon\s*:\s*([0-9.]+)",
    "shannon_range": r"Shannon range\s*:\s*([0-9.]+)",

    "mean_action_fisher": r"Mean action Fisher\s*:\s*([0-9.]+)",
    "min_action_fisher": r"Min action Fisher\s*:\s*([0-9.]+)",
    "max_action_fisher": r"Max action Fisher\s*:\s*([0-9.]+)",
    "action_fisher_range": r"Fisher range\s*:\s*([0-9.]+)",

    "mean_lexical_fisher": r"Mean lexical Fisher\s*:\s*([0-9.]+)",
    "min_lexical_fisher": r"Min lexical Fisher\s*:\s*([0-9.]+)",
    "max_lexical_fisher": r"Max lexical Fisher\s*:\s*([0-9.]+)",
    "lex_fisher_range": r"Lex Fisher range\s*:\s*([0-9.]+)",

    "avg_zipf": r"Average Zipf\s*:\s*([0-9.]+)",
    "median_zipf": r"Median Zipf\s*:\s*([0-9.]+)",
    "min_zipf": r"Minimum Zipf\s*:\s*([0-9.]+)",
    "avg_info_bits": r"Avg information bits\s*:\s*([0-9.]+)",
    "rare_count": r"Rare words < 3\.0\s*:\s*([0-9.]+)",
    "very_rare_count": r"Very rare < 2\.5\s*:\s*([0-9.]+)",
    "rare_density": r"Rare density\s*:\s*([0-9.]+)",
    "very_rare_density": r"Very rare density\s*:\s*([0-9.]+)",

    "modifier_links": r"Modifier links\s*:\s*([0-9.]+)",
    "agent_links": r"Agent-like noun links\s*:\s*([0-9.]+)",
    "base_noun_count": r"Base noun count\s*:\s*([0-9.]+)",
    "weighted_noun_mass": r"Weighted noun mass\s*:\s*([0-9.]+)",
    "modifier_density": r"Modifier density\s*:\s*([0-9.]+)",
    "agent_density": r"Agent density\s*:\s*([0-9.]+)",
    "agency_noun_ratio": r"Agency / noun ratio\s*:\s*([0-9.]+)",
}

POS_PATTERNS = {
    "noun_pct": r"^NOUN\s+[0-9]+\s+([0-9.]+)%",
    "verb_pct": r"^VERB\s+[0-9]+\s+([0-9.]+)%",
    "adj_pct": r"^ADJ\s+[0-9]+\s+([0-9.]+)%",
    "adv_pct": r"^ADV\s+[0-9]+\s+([0-9.]+)%",
    "pron_pct": r"^PRON\s+[0-9]+\s+([0-9.]+)%",
    "neg_pct": r"^NEG\s+[0-9]+\s+([0-9.]+)%",
}


def find_first_number(pattern, text, default=0.0, flags=re.MULTILINE):
    m = re.search(pattern, text, flags)
    if not m:
        return default
    try:
        return float(m.group(1))
    except Exception:
        return default


def parse_analysis_file(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    rows = []
    for idx, match in enumerate(SONG_RE.finditer(text), start=1):
        title = match.group(1).strip()
        body = match.group(2)

        row = {
            "index": idx,
            "title": title,
            "source_file": str(path),
        }

        for key, pat in FIELD_PATTERNS.items():
            row[key] = find_first_number(pat, body)

        for key, pat in POS_PATTERNS.items():
            row[key] = find_first_number(pat, body)

        rows.append(row)

    # Fallback: when a file contains one song report only
    if not rows and "SONG:" in text:
        m = re.search(r"^SONG:\s*(.+)$", text, re.MULTILINE)
        title = m.group(1).strip() if m else path.stem
        row = {
            "index": 1,
            "title": title,
            "source_file": str(path),
        }
        for key, pat in FIELD_PATTERNS.items():
            row[key] = find_first_number(pat, text)
        for key, pat in POS_PATTERNS.items():
            row[key] = find_first_number(pat, text)
        rows.append(row)

    return rows


def discover_analysis_files(folder):
    folder = Path(folder)
    candidates = []

    patterns = [
        "*_analysis.txt",
        "analysis.txt",
        "*analysis*.txt",
    ]

    seen = set()
    for pat in patterns:
        for p in folder.rglob(pat):
            if p.is_file() and p not in seen:
                seen.add(p)
                candidates.append(p)

    return sorted(candidates)


def parse_album_folder(folder):
    files = discover_analysis_files(folder)
    all_rows = []

    for f in files:
        rows = parse_analysis_file(f)
        all_rows.extend(rows)

    # remove duplicate song titles if several analysis files were found
    dedup = []
    seen_titles = set()
    for r in all_rows:
        key = (r["title"].lower(), r["index"])
        if key in seen_titles:
            continue
        seen_titles.add(key)
        dedup.append(r)

    for i, r in enumerate(dedup, start=1):
        r["index"] = i

    return files, dedup

def parse_albums_root(folder):
    """Parse all album folders under an artist/root output directory.

    The function groups analysis files by their parent folder.
    Expected structure:
        Output/Metallica/1983_Kill_Em_All/<album>_analysis.txt
        Output/Metallica/1984_Ride_The_Lightning/<album>_analysis.txt

    It also works if the selected folder itself is one album folder.
    """
    folder = Path(folder)
    analysis_files = discover_analysis_files(folder)
    album_dirs = sorted({p.parent for p in analysis_files})

    album_rows = []
    for idx, album_dir in enumerate(album_dirs, start=1):
        files, rows = parse_album_folder(album_dir)
        if not rows:
            continue

        s = album_summary(rows)
        s["index"] = idx
        s["album"] = album_dir.name
        s["folder"] = str(album_dir)
        s["analysis_files"] = len(files)
        s["song_count"] = len(rows)
        album_rows.append(s)

    # stable sort: year-prefixed album folders automatically sort chronologically
    album_rows = sorted(album_rows, key=lambda r: r.get("album", ""))
    for i, r in enumerate(album_rows, start=1):
        r["index"] = i

    return album_rows



def parse_albums_root_full(folder):
    """Parse albums and also keep all songs grouped by album.

    Returns:
        album_rows : one row per album
        song_rows  : one row per song with album metadata
    """
    folder = Path(folder)
    analysis_files = discover_analysis_files(folder)
    album_dirs = sorted({p.parent for p in analysis_files}, key=lambda p: p.name)

    album_rows = []
    song_rows = []

    for album_idx, album_dir in enumerate(album_dirs, start=1):
        files, rows = parse_album_folder(album_dir)
        if not rows:
            continue

        s = album_summary(rows)
        s["index"] = album_idx
        s["album"] = album_dir.name
        s["folder"] = str(album_dir)
        s["analysis_files"] = len(files)
        s["song_count"] = len(rows)
        album_rows.append(s)

        for song_idx, r in enumerate(rows, start=1):
            rr = dict(r)
            rr["album"] = album_dir.name
            rr["album_index"] = album_idx
            rr["song_in_album_index"] = song_idx
            rr["folder"] = str(album_dir)
            song_rows.append(rr)

    album_rows = sorted(album_rows, key=lambda r: r.get("album", ""))
    album_order = {r["album"]: i + 1 for i, r in enumerate(album_rows)}

    for i, r in enumerate(album_rows, start=1):
        r["index"] = i

    song_rows = sorted(
        song_rows,
        key=lambda r: (
            album_order.get(r.get("album", ""), 999999),
            int(r.get("song_in_album_index", r.get("index", 0))),
        ),
    )

    for global_i, r in enumerate(song_rows, start=1):
        r["global_index"] = global_i

    return album_rows, song_rows


def gini_coefficient(values):
    """Gini coefficient for non-negative song-level metric values.

    Returns 0.0 for empty, constant-zero, or invalid inputs.
    In LYRICA this measures how unevenly a metric is distributed
    across songs inside an album.
    """
    vals = []
    for v in values:
        try:
            x = float(v)
        except Exception:
            continue
        if not math.isfinite(x):
            continue
        # Metrics should be non-negative. Negative values are shifted to 0.
        vals.append(max(0.0, x))

    n = len(vals)
    if n == 0:
        return 0.0

    vals.sort()
    total = sum(vals)
    if total <= 1e-12:
        return 0.0

    weighted = sum((i + 1) * x for i, x in enumerate(vals))
    g = (2.0 * weighted) / (n * total) - (n + 1.0) / n
    return max(0.0, min(1.0, float(g)))


def metric_values(rows, key):
    vals = []
    for r in rows:
        v = r.get(key, 0.0)
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            vals.append(float(v))
    return vals


def album_summary(rows):
    if not rows:
        return {}

    def mean(key):
        vals = [r.get(key, 0.0) for r in rows if isinstance(r.get(key, 0.0), (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def total(key):
        return sum(r.get(key, 0.0) for r in rows if isinstance(r.get(key, 0.0), (int, float)))

    return {
        "songs": len(rows),
        "total_words": total("words"),
        "total_unique_words": total("unique_words"),
        "mean_lexical_density": mean("lexical_density"),
        "mean_repeated_line_mass": mean("repeated_line_mass"),
        "mean_shannon": mean("mean_block_shannon"),
        "mean_lexical_fisher": mean("mean_lexical_fisher"),
        "mean_action_fisher": mean("mean_action_fisher"),
        "mean_rare_density": mean("rare_density"),
        "mean_agency_ratio": mean("agency_noun_ratio"),

        # Album-level distribution / inequality descriptors.
        # These do not replace the mean values; they show whether an album is
        # balanced or dominated by one/few songs for the chosen metric.
        "gini_action_fisher": gini_coefficient(metric_values(rows, "mean_action_fisher")),
        "gini_lexical_fisher": gini_coefficient(metric_values(rows, "mean_lexical_fisher")),
        "gini_shannon": gini_coefficient(metric_values(rows, "mean_block_shannon")),
        "gini_rare_density": gini_coefficient(metric_values(rows, "rare_density")),
        "gini_agency_ratio": gini_coefficient(metric_values(rows, "agency_noun_ratio")),

        "max_action_fisher": max(metric_values(rows, "mean_action_fisher") or [0.0]),
        "max_lexical_fisher": max(metric_values(rows, "mean_lexical_fisher") or [0.0]),
        "max_shannon": max(metric_values(rows, "mean_block_shannon") or [0.0]),
        "sum_action_fisher": total("mean_action_fisher"),
        "sum_lexical_fisher": total("mean_lexical_fisher"),
    }


# ============================================================
# GUI
# ============================================================

class LyricaAlbumVisualizer(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("LYRICA Album Visualizer v1.3")
        self.geometry("1400x820")

        self.folder = None
        self.files = []
        self.rows = []
        self.album_rows = []
        self.view_mode = "songs"
        self.root_mode = False
        self.album_color_map = {}
        self._resize_after_id = None
        self._delayed_fit_ids = []
        self._last_canvas_size = (0, 0)
        self._last_window_state = None
        self._redraw_after_id = None
        self._export_mode = False
        self._bar_patch_meta = {}
        self._ytick_label_meta = []
        self._grouped_song_position_to_index = {}
        self.selected_bar_patch = None
        self.selected_bar_key = None

        self.create_widgets()

    def create_widgets(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Button(top, text="Open Album Folder", command=self.open_album_folder).pack(side="left")
        ttk.Button(top, text="Open Albums Root", command=self.open_albums_root).pack(side="left", padx=8)
        ttk.Button(top, text="Export Parsed CSV", command=self.export_csv).pack(side="left", padx=8)
        ttk.Button(top, text="Save Current Figure PNG", command=self.save_current_figure).pack(side="left")
        ttk.Button(top, text="Force Redraw", command=self.draw_selected_chart).pack(side="left", padx=8)

        self.lbl_folder = ttk.Label(top, text="No folder loaded")
        self.lbl_folder.pack(side="left", padx=12)

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=1)
        main.add(right, weight=4)

        ttk.Label(left, text="Charts").pack(anchor="w")

        self.chart_list = tk.Listbox(left, exportselection=False)
        self.chart_list.pack(fill="x", pady=(0, 8))
        self.chart_list.bind("<<ListboxSelect>>", self.on_chart_select)

        charts = [
            "Album summary",
            "Mean Shannon by song",
            "Lexical density by song",
            "Repeated line mass by song",
            "Rare density by song",
            "Agency ratio by song",
            "Mean lexical Fisher by song",
            "Mean action Fisher by song",
            "Vocabulary size by song",
            "POS distribution by song",
            "Vocabulary growth",
            "Shannon vs lexical density",
            "ALBUMS: integrated score",
            "ALBUMS: mean Shannon",
            "ALBUMS: lexical density",
            "ALBUMS: repeated line mass",
            "ALBUMS: rare density",
            "ALBUMS: agency ratio",
            "ALBUMS: Fisher comparison",
            "ALBUMS: Action Fisher Gini",
            "ALBUMS: Lexical Fisher Gini",
            "ALBUMS: Shannon Gini",
            "ALBUMS: Rare Density Gini",
            "ALBUMS: Gini comparison",
            "ALBUMS: word totals",
        ]

        for c in charts:
            self.chart_list.insert(tk.END, c)

        ttk.Label(left, text="Songs / parsed rows").pack(anchor="w")

        self.song_list = tk.Listbox(left, exportselection=False)
        self.song_list.pack(fill="both", expand=True)

        self.info_text = tk.Text(left, height=12, wrap="word", font=("DejaVu Sans Mono", 9))
        self.info_text.pack(fill="x", pady=(8, 0))

        fig_w, fig_h = self.initial_figure_size()
        self.fig = Figure(figsize=(fig_w, fig_h), dpi=100, facecolor="white")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("white")

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.mpl_connect("pick_event", self.on_pick_bar)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)
        self.canvas_widget.bind("<Configure>", self.on_canvas_resize, add="+")
        right.bind("<Configure>", self.on_canvas_resize, add="+")
        main.bind("<Configure>", self.on_canvas_resize, add="+")
        self.bind("<Configure>", self.on_canvas_resize, add="+")
        self.bind("<Map>", self.on_canvas_resize, add="+")
        self.bind("<Visibility>", self.on_canvas_resize, add="+")
        self.bind("<Expose>", self.on_canvas_resize, add="+")

        toolbar = NavigationToolbar2Tk(self.canvas, right)
        toolbar.update()

        self.chart_list.selection_set(0)
        self.after(250, self.force_canvas_fit)
        self.after(700, self.force_canvas_fit)

    def initial_figure_size(self):
        sw = max(1024, int(self.winfo_screenwidth()))
        sh = max(720, int(self.winfo_screenheight()))
        return max(7.0, sw * 0.62 / 100.0), max(5.0, sh * 0.62 / 100.0)

    def on_canvas_resize(self, event=None):
        """Debounced resize handler.

        Tk sometimes sends <Configure> before the inner TkAgg canvas has its
        final size, especially when the window is maximized, restored, tiled,
        or when the PanedWindow sash is moved.  Therefore the real widget size
        is read later from canvas_widget, not trusted from the raw event.
        """
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass

        self._resize_after_id = self.after(80, self.force_canvas_fit)

        # Extra passes catch maximize / restore / tiling transitions on Linux.
        for delay in (220, 520, 900):
            self.after(delay, self.force_canvas_fit)

    def force_canvas_fit(self):
        """Make the Matplotlib figure match the visible canvas and redraw if needed."""
        self._resize_after_id = None

        if not hasattr(self, "canvas_widget"):
            return

        self.update_idletasks()
        width_px = int(self.canvas_widget.winfo_width())
        height_px = int(self.canvas_widget.winfo_height())

        if width_px < 120 or height_px < 120:
            return

        state = None
        try:
            state = self.state()
        except Exception:
            state = None

        old_w, old_h = self._last_canvas_size
        size_changed = abs(width_px - old_w) >= 3 or abs(height_px - old_h) >= 3
        state_changed = state != self._last_window_state

        if not size_changed and not state_changed:
            return

        self._last_canvas_size = (width_px, height_px)
        self._last_window_state = state
        self.resize_figure_to_canvas(width_px, height_px)

        # On maximize/restore some TkAgg backends keep stale layout until a real redraw.
        if self.rows or self.album_rows:
            if self._redraw_after_id is not None:
                try:
                    self.after_cancel(self._redraw_after_id)
                except Exception:
                    pass
            self._redraw_after_id = self.after(120, self.redraw_current_chart_after_resize)

    def redraw_current_chart_after_resize(self):
        self._redraw_after_id = None
        if self.rows or self.album_rows:
            self.draw_selected_chart()

    def resize_figure_to_canvas(self, width_px, height_px):
        self.fig.set_facecolor("white")
        dpi = float(self.fig.get_dpi())
        self.fig.set_size_inches(
            max(5.0, width_px / dpi),
            max(4.0, height_px / dpi),
            forward=True,
        )
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()

    def open_album_folder(self):
        initial_dir = Path.cwd()
        folder = filedialog.askdirectory(
            title="Select LYRICA album output folder",
            initialdir=str(initial_dir),
        )

        if not folder:
            return

        try:
            files, rows = parse_album_folder(folder)

            if not files:
                messagebox.showwarning(
                    "No analysis files",
                    "No *_analysis.txt or analysis.txt files were found in this folder tree.",
                )
                return

            if not rows:
                messagebox.showwarning(
                    "No song data",
                    "Analysis files were found, but no SONG blocks were parsed.",
                )
                return

            self.folder = Path(folder)
            self.files = files
            self.rows = rows
            self.album_rows = []
            self.view_mode = "songs"
            self.root_mode = False
            self.album_color_map = {}

            self.lbl_folder.config(text=str(self.folder))
            self.refresh_song_list()
            self.refresh_info()

            self.draw_selected_chart()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def open_albums_root(self):
        initial_dir = Path.cwd()
        folder = filedialog.askdirectory(
            title="Select LYRICA artist/albums root folder",
            initialdir=str(initial_dir),
        )

        if not folder:
            return

        try:
            album_rows, song_rows = parse_albums_root_full(folder)

            if not album_rows:
                messagebox.showwarning(
                    "No albums parsed",
                    "No album analysis files were found under this folder tree.",
                )
                return

            self.folder = Path(folder)
            self.files = []
            self.rows = song_rows
            self.album_rows = album_rows
            self.view_mode = "albums"
            self.root_mode = True
            self.rebuild_album_colors()

            self.lbl_folder.config(text=str(self.folder))
            self.refresh_song_list()
            self.refresh_info()

            # Select first album-level chart
            for i in range(self.chart_list.size()):
                if self.chart_list.get(i) == "ALBUMS: integrated score":
                    self.chart_list.selection_clear(0, tk.END)
                    self.chart_list.selection_set(i)
                    break

            self.draw_selected_chart()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh_song_list(self):
        self.song_list.delete(0, tk.END)

        if self.view_mode == "albums":
            for r in self.album_rows:
                self.song_list.insert(tk.END, f"{int(r['index']):02d}. {r['album']}  [{int(r['song_count'])} songs]")
            return

        for r in self.rows:
            self.song_list.insert(tk.END, f"{int(r['index']):02d}. {r['title']}")

    def refresh_info(self):
        self.info_text.delete("1.0", tk.END)

        lines = []
        lines.append("LYRICA ALBUM VISUALIZER")
        lines.append("=" * 28)

        if self.view_mode == "albums":
            lines.append("Mode          : album integration")
            lines.append(f"Albums parsed : {len(self.album_rows)}")
            lines.append(f"Songs parsed  : {len(self.rows)}")
            lines.append("")
            if self.album_rows:
                total_songs = sum(float(r.get("song_count", 0.0)) for r in self.album_rows)
                total_words = sum(float(r.get("total_words", 0.0)) for r in self.album_rows)
                mean_sh = sum(float(r.get("mean_shannon", 0.0)) for r in self.album_rows) / len(self.album_rows)
                mean_ld = sum(float(r.get("mean_lexical_density", 0.0)) for r in self.album_rows) / len(self.album_rows)
                lines.append(f"Total songs   : {total_songs:.0f}")
                lines.append(f"Total words   : {total_words:.0f}")
                lines.append(f"Mean Shannon  : {mean_sh:.3f}")
                lines.append(f"Mean Lex.Dens.: {mean_ld:.3f}")
        else:
            s = album_summary(self.rows)
            lines.append("Mode          : song-level album")
            lines.append(f"Analysis files: {len(self.files)}")
            lines.append(f"Songs parsed  : {len(self.rows)}")
            lines.append("")
            if s:
                lines.append(f"Total words   : {s['total_words']:.0f}")
                lines.append(f"Mean Shannon  : {s['mean_shannon']:.3f}")
                lines.append(f"Mean Lex.Dens.: {s['mean_lexical_density']:.3f}")
                lines.append(f"Mean Repeat   : {s['mean_repeated_line_mass']:.3f}")
                lines.append(f"Mean Rare     : {s['mean_rare_density']:.3f}")
                lines.append(f"Mean Agency   : {s['mean_agency_ratio']:.3f}")

        self.info_text.insert(tk.END, "\n".join(lines))

    def on_chart_select(self, event=None):
        self.draw_selected_chart()

    def get_selected_chart(self):
        sel = self.chart_list.curselection()
        if not sel:
            return "Album summary"
        return self.chart_list.get(sel[0])

    def clear_plot(self):
        # Keep selected_bar_key so selection can survive a redraw,
        # but remove stale Matplotlib artist references.
        self._bar_patch_meta = {}
        self._ytick_label_meta = []
        self.selected_bar_patch = None
        self.fig.clear()
        self.fig.set_facecolor("white")
        self.fig.patch.set_alpha(1.0)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("white")
        self.ax.patch.set_alpha(1.0)

    def rebuild_album_colors(self):
        """Assign one stable color to every album in the current root view."""
        albums = []
        for r in self.album_rows:
            a = r.get("album", "Album")
            if a not in albums:
                albums.append(a)
        if not albums:
            for r in self.rows:
                a = r.get("album", "Album")
                if a not in albums:
                    albums.append(a)

        cmap = matplotlib.cm.get_cmap("tab20", max(1, len(albums)))
        self.album_color_map = {album: cmap(i) for i, album in enumerate(albums)}

    def album_color(self, album):
        if not self.album_color_map:
            self.rebuild_album_colors()
        return self.album_color_map.get(album, "tab:blue")

    def row_album_colors(self):
        """Song bar colors that preserve one distinct color per album.

        Inside each album, consecutive songs alternate between a stronger and
        a paler variant of the same album hue.  This keeps album identity while
        making long horizontal rows easier to follow.
        """
        if not self.root_mode:
            return readable_row_colors(len(self.rows))

        out = []
        for i, r in enumerate(self.rows):
            base = self.album_color(r.get("album", "Album"))
            local_i = int(r.get("song_in_album_index", i + 1)) - 1
            if local_i % 2 == 0:
                c = darken(base, 0.05)
                out.append((c[0], c[1], c[2], 0.92))
            else:
                c = lighten(base, 0.42)
                out.append((c[0], c[1], c[2], 0.78))
        return out

    def row_pair_colors(self, n=None):
        if n is None:
            n = len(self.rows)
        if not self.root_mode:
            return readable_pair_colors(n)
        base = self.row_album_colors()[:int(n)]
        pale = []
        for c in base:
            cc = mix_with(c, (1, 1, 1, 1), 0.48)
            pale.append((cc[0], cc[1], cc[2], 0.50))
        return base, pale

    def album_bar_colors(self):
        """Album-level colors stay in the original album palette."""
        if not self.album_rows:
            return None
        return [self.album_color(r.get("album", "Album")) for r in self.album_rows]

    def plain_alternating_bar_colors(self, n, base="tab:blue"):
        return readable_row_colors(int(n))

    def add_album_legend(self):
        if not self.album_color_map:
            return
        import matplotlib.patches as mpatches
        handles = [mpatches.Patch(color=c, label=a) for a, c in self.album_color_map.items()]
        if handles:
            self.ax.legend(handles=handles, title="Albums", loc="best", fontsize=8)

    def shade_album_groups(self):
        """Light background bands behind song rows in root mode."""
        if not self.root_mode or not self.rows:
            return
        current = None
        start = None
        for i, r in enumerate(self.rows + [{"album": None}]):
            album = r.get("album")
            if album != current:
                if current is not None and start is not None:
                    self.ax.axhspan(start - 0.5, i - 0.5, color=self.album_color(current), alpha=0.08, zorder=0)
                current = album
                start = i

    def labels(self):
        if self.root_mode:
            return [
                f"{int(r.get('song_in_album_index', r.get('index', 0))):02d}. {r.get('title', '')}"
                for r in self.rows
            ]
        return [f"{int(r['index']):02d}. {r['title']}" for r in self.rows]

    def values(self, key):
        return [float(r.get(key, 0.0)) for r in self.rows]

    def album_labels(self):
        return [f"{int(r['index']):02d}. {r['album']}" for r in self.album_rows]

    def album_values(self, key):
        return [float(r.get(key, 0.0)) for r in self.album_rows]

    def integrated_album_score_values(self):
        """Simple 0..1 integrated profile for visual ranking.

        This is not a new linguistic metric. It is only a visualization index
        combining already exported album descriptors after min-max normalization.
        """
        keys = [
            "mean_shannon",
            "mean_lexical_density",
            "mean_repeated_line_mass",
            "mean_rare_density",
            "mean_agency_ratio",
        ]
        cols = []
        for key in keys:
            vals = self.album_values(key)
            if not vals:
                continue
            lo = min(vals)
            hi = max(vals)
            if hi <= lo + 1e-12:
                cols.append([0.0 for _ in vals])
            else:
                cols.append([(v - lo) / (hi - lo + 1e-12) for v in vals])
        if not cols:
            return []
        return [sum(col[i] for col in cols) / len(cols) for i in range(len(cols[0]))]

    def register_bars(self, bars, kind="song", indices=None, series=None):
        """Register Matplotlib bar patches for click selection.

        If a chart is redrawn while a row is selected, the old Patch object is
        destroyed.  The logical key is preserved and the newly created Patch is
        styled again here.
        """
        if bars is None:
            return
        try:
            patches = list(bars.patches)
        except Exception:
            patches = list(bars)
        if indices is None:
            indices = list(range(len(patches)))
        for patch, idx in zip(patches, indices):
            idx = int(idx)
            series_key = series or ""
            try:
                patch.set_picker(True)
                patch.set_pickradius(4)
            except Exception:
                pass
            normal_lw = float(patch.get_linewidth() or 0.25)
            normal_edge = patch.get_edgecolor()
            self._bar_patch_meta[id(patch)] = {
                "kind": kind,
                "index": idx,
                "series": series_key,
                "normal_lw": normal_lw,
                "normal_edge": normal_edge,
            }

            if self.selected_bar_key == (kind, idx, series_key):
                self.selected_bar_patch = patch
                patch.set_edgecolor("red")
                patch.set_linewidth(3.2)
                patch.set_zorder(10)

    def on_pick_bar(self, event):
        patch = getattr(event, "artist", None)
        if patch is None or id(patch) not in self._bar_patch_meta:
            return
        meta = self._bar_patch_meta.get(id(patch), {})
        key = (meta.get("kind"), meta.get("index"), meta.get("series"))

        # Toggle off if the same bar is clicked again.
        if self.selected_bar_patch is patch and self.selected_bar_key == key:
            self.restore_bar_style(patch)
            self.selected_bar_patch = None
            self.selected_bar_key = None
            self.apply_label_highlights()
            self.canvas.draw_idle()
            return

        if self.selected_bar_patch is not None:
            self.restore_bar_style(self.selected_bar_patch)

        self.selected_bar_patch = patch
        self.selected_bar_key = key
        patch.set_edgecolor("red")
        patch.set_linewidth(3.2)
        patch.set_zorder(10)

        self.sync_selection_to_panel(meta)
        self.apply_label_highlights()
        self.canvas.draw_idle()

    def restore_bar_style(self, patch):
        meta = self._bar_patch_meta.get(id(patch), {})
        try:
            patch.set_edgecolor(meta.get("normal_edge", "black"))
            patch.set_linewidth(meta.get("normal_lw", 0.25))
            patch.set_zorder(2)
        except Exception:
            pass

    def sync_selection_to_panel(self, meta):
        """Show selected bar information in the left panel."""
        kind = meta.get("kind")
        idx = int(meta.get("index", -1))
        if kind == "album" and 0 <= idx < len(self.album_rows):
            self.song_list.selection_clear(0, tk.END)
            if self.view_mode == "albums":
                self.song_list.selection_set(idx)
                self.song_list.see(idx)
            r = self.album_rows[idx]
            self.show_metric_row(r, title=f"SELECTED ALBUM: {r.get('album', '')}")
        elif kind == "song" and 0 <= idx < len(self.rows):
            if self.view_mode != "albums":
                self.song_list.selection_clear(0, tk.END)
                self.song_list.selection_set(idx)
                self.song_list.see(idx)
            r = self.rows[idx]
            album = r.get("album", "")
            prefix = f"{album} / " if album else ""
            self.show_metric_row(r, title=f"SELECTED SONG: {prefix}{r.get('title', '')}")

    def _selected_kind_index(self):
        if not self.selected_bar_key:
            return None, None
        try:
            kind, idx, _series = self.selected_bar_key
            return kind, int(idx)
        except Exception:
            return None, None

    def _empty_label_bbox(self):
        return dict(facecolor="none", edgecolor="none", alpha=0.0, pad=0.0)

    def register_simple_song_tick_labels(self, positions, kind="song"):
        """Store y tick label objects so click selection can highlight text."""
        self._ytick_label_meta = []
        ticks = list(self.ax.get_yticklabels())
        for tick, pos in zip(ticks, positions):
            self._ytick_label_meta.append({
                "tick": tick,
                "kind": kind,
                "index": int(pos),
                "album": None,
            })
        self.apply_label_highlights()

    def apply_label_highlights(self):
        """Yellow-highlight the selected song/album name in the y-axis labels."""
        selected_kind, selected_idx = self._selected_kind_index()

        for item in getattr(self, "_ytick_label_meta", []):
            tick = item.get("tick")
            if tick is None:
                continue
            kind = item.get("kind")
            idx = item.get("index")

            # Base style
            tick.set_color("black")
            tick.set_bbox(self._empty_label_bbox())

            if kind == "album_header":
                tick.set_fontweight("bold")
                tick.set_fontsize(8)
                album = item.get("album")
                if album is not None:
                    bg = lighten(self.album_color(album), 0.72)
                    tick.set_bbox(dict(
                        facecolor=bg,
                        edgecolor="none",
                        alpha=0.45,
                        boxstyle="round,pad=0.18",
                    ))
                continue

            tick.set_fontweight("normal")

            if kind == selected_kind and idx == selected_idx:
                tick.set_fontweight("bold")
                tick.set_bbox(dict(
                    facecolor="#fff3a6",
                    edgecolor="#d6a900",
                    linewidth=0.7,
                    alpha=0.92,
                    boxstyle="round,pad=0.22",
                ))

    def show_metric_row(self, row, title="SELECTED ROW"):
        self.info_text.delete("1.0", tk.END)
        lines = [title, "=" * min(60, max(12, len(title)))]
        preferred = [
            "album", "song_in_album_index", "index", "song_count",
            "words", "unique_words", "total_words", "total_unique_words",
            "lexical_density", "repeated_line_mass", "mean_block_shannon",
            "mean_shannon", "mean_lexical_fisher", "mean_action_fisher",
            "rare_density", "mean_rare_density", "agency_noun_ratio", "mean_agency_ratio",
            "noun_pct", "verb_pct", "adj_pct", "pron_pct",
        ]
        used = set()
        for k in preferred:
            if k in row:
                used.add(k)
                v = row.get(k)
                if isinstance(v, float):
                    lines.append(f"{k:24s}: {v:.6g}")
                else:
                    lines.append(f"{k:24s}: {v}")
        for k in sorted(row.keys()):
            if k in used or k in {"source_file", "folder"}:
                continue
            v = row.get(k)
            if isinstance(v, float):
                lines.append(f"{k:24s}: {v:.6g}")
            else:
                lines.append(f"{k:24s}: {v}")
        self.info_text.insert(tk.END, "\n".join(lines))

    def draw_selected_chart(self):
        chart = self.get_selected_chart()

        if chart.startswith("ALBUMS:"):
            if not self.album_rows:
                return
            self.clear_plot()
            if chart == "ALBUMS: integrated score":
                self.plot_album_bar_values(self.integrated_album_score_values(), "Integrated Album Score", "Normalized score")
            elif chart == "ALBUMS: mean Shannon":
                self.plot_album_bar("mean_shannon", "Mean Shannon by Album", "Mean block Shannon [bits]")
            elif chart == "ALBUMS: lexical density":
                self.plot_album_bar("mean_lexical_density", "Lexical Density by Album", "Mean lexical density")
            elif chart == "ALBUMS: repeated line mass":
                self.plot_album_bar("mean_repeated_line_mass", "Repeated Line Mass by Album", "Mean repeated line mass")
            elif chart == "ALBUMS: rare density":
                self.plot_album_bar("mean_rare_density", "Rare Word Density by Album", "Mean rare density")
            elif chart == "ALBUMS: agency ratio":
                self.plot_album_bar("mean_agency_ratio", "Agency / Noun Ratio by Album", "Mean agency / noun ratio")
            elif chart == "ALBUMS: Fisher comparison":
                self.plot_album_dual_line("mean_lexical_fisher", "mean_action_fisher", "Lexical Fisher vs Action Fisher by Album", "Mean Fisher")
            elif chart == "ALBUMS: Action Fisher Gini":
                self.plot_album_bar("gini_action_fisher", "Action Fisher Gini by Album", "Gini coefficient (0=balanced, 1=concentrated)")
            elif chart == "ALBUMS: Lexical Fisher Gini":
                self.plot_album_bar("gini_lexical_fisher", "Lexical Fisher Gini by Album", "Gini coefficient (0=balanced, 1=concentrated)")
            elif chart == "ALBUMS: Shannon Gini":
                self.plot_album_bar("gini_shannon", "Shannon Gini by Album", "Gini coefficient (0=balanced, 1=concentrated)")
            elif chart == "ALBUMS: Rare Density Gini":
                self.plot_album_bar("gini_rare_density", "Rare Density Gini by Album", "Gini coefficient (0=balanced, 1=concentrated)")
            elif chart == "ALBUMS: Gini comparison":
                self.plot_album_gini_comparison()
            elif chart == "ALBUMS: word totals":
                self.plot_album_dual_bar("total_words", "total_unique_words", "Total and Unique Words by Album", "Count")
            else:
                self.plot_album_bar_values(self.integrated_album_score_values(), "Integrated Album Score", "Normalized score")
            force_opaque_figure(self.fig)
            self.fig.tight_layout()
            self.canvas.draw()
            return

        if not self.rows:
            return

        self.clear_plot()

        if chart == "Album summary":
            self.plot_album_summary()
        elif chart == "Mean Shannon by song":
            self.plot_bar("mean_block_shannon", "Mean Shannon by Song", "Mean block Shannon [bits]")
        elif chart == "Lexical density by song":
            self.plot_bar("lexical_density", "Lexical Density by Song", "Lexical density")
        elif chart == "Repeated line mass by song":
            self.plot_bar("repeated_line_mass", "Repeated Line Mass by Song", "Repeated line mass")
        elif chart == "Rare density by song":
            self.plot_bar("rare_density", "Rare Word Density by Song", "Rare density")
        elif chart == "Agency ratio by song":
            self.plot_bar("agency_noun_ratio", "Agency / Noun Ratio by Song", "Agency / noun ratio")
        elif chart == "Mean lexical Fisher by song":
            self.plot_bar("mean_lexical_fisher", "Mean Lexical Fisher by Song", "Mean lexical Fisher")
        elif chart == "Mean action Fisher by song":
            self.plot_bar("mean_action_fisher", "Mean Action Fisher by Song", "Mean action Fisher")
        elif chart == "Vocabulary size by song":
            self.plot_dual_bar("words", "unique_words", "Vocabulary Size by Song", "Count")
        elif chart == "POS distribution by song":
            self.plot_pos_lines()
        elif chart == "Vocabulary growth":
            self.plot_vocabulary_growth()
        elif chart == "Shannon vs lexical density":
            self.plot_scatter("lexical_density", "mean_block_shannon",
                              "Shannon vs Lexical Density",
                              "Lexical density", "Mean block Shannon [bits]")
        else:
            self.plot_album_summary()

        force_opaque_figure(self.fig)
        self.fig.tight_layout()
        self.canvas.draw()

    def grouped_song_positions(self):
        """Build y positions with album header rows for root-mode song charts."""
        self._grouped_song_position_to_index = {}
        self._grouped_header_position_to_album = {}

        if not self.root_mode:
            labels = self.labels()
            return list(range(len(labels))), labels, list(range(len(labels))), None

        positions = []
        labels = []
        bar_positions = []
        header_positions = []
        current_album = None
        y = 0

        for song_idx, r in enumerate(self.rows):
            album = r.get("album", "Album")
            if album != current_album:
                current_album = album
                positions.append(y)
                labels.append(f"{album}")
                header_positions.append(y)
                self._grouped_header_position_to_album[y] = album
                y += 1

            positions.append(y)
            labels.append(f"  {int(r.get('song_in_album_index', r.get('index', 0))):02d}. {r.get('title', '')}")
            bar_positions.append(y)
            self._grouped_song_position_to_index[y] = song_idx
            y += 1

        return positions, labels, bar_positions, header_positions

    def style_grouped_y_axis(self, positions, labels, header_positions=None):
        self.ax.set_yticks(positions)
        self.ax.set_yticklabels(labels, fontsize=7)
        self.ax.invert_yaxis()

        header_set = set(header_positions or [])
        self._ytick_label_meta = []
        for tick, pos in zip(self.ax.get_yticklabels(), positions):
            if pos in header_set:
                self._ytick_label_meta.append({
                    "tick": tick,
                    "kind": "album_header",
                    "index": -1,
                    "album": getattr(self, "_grouped_header_position_to_album", {}).get(pos),
                })
            else:
                self._ytick_label_meta.append({
                    "tick": tick,
                    "kind": "song",
                    "index": int(getattr(self, "_grouped_song_position_to_index", {}).get(pos, -1)),
                    "album": None,
                })

        if header_positions:
            for hp in header_positions:
                self.ax.axhline(hp + 0.5, linewidth=0.8, alpha=0.25)

        self.apply_label_highlights()

    def autosize_for_rows(self, n_rows):
        """Fit the live figure to the actual visible canvas.

        The previous version increased the live figure height according to the
        number of rows.  That could fight Tk's geometry manager and made
        maximize/restore unreliable.  The live view now always follows the
        canvas size; exported PNGs can still be taller.
        """
        if getattr(self, "_export_mode", False):
            # Exported figures may be taller; live figures must follow the canvas.
            return
        widget = getattr(self, "canvas_widget", None)
        if widget is None:
            return
        self.update_idletasks()
        w_px = max(500, int(widget.winfo_width()))
        h_px = max(400, int(widget.winfo_height()))
        dpi = float(self.fig.get_dpi())
        self.fig.set_size_inches(w_px / dpi, h_px / dpi, forward=True)

    def plot_bar(self, key, title, ylabel):
        vals = self.values(key)

        if self.root_mode:
            positions, labels, bar_positions, header_positions = self.grouped_song_positions()
            self.autosize_for_rows(len(positions))
            self.shade_album_groups()
            bars = self.ax.barh(bar_positions, vals, color=self.row_album_colors(), edgecolor="black", linewidth=0.25)
            self.register_bars(bars, kind="song", indices=list(range(len(vals))), series=key)
            self.style_grouped_y_axis(positions, labels, header_positions)
            self.add_album_legend()
        else:
            labels = self.labels()
            y = list(range(len(vals)))
            self.autosize_for_rows(len(y))
            bars = self.ax.barh(y, vals, color=self.plain_alternating_bar_colors(len(y)), edgecolor="black", linewidth=0.25)
            self.register_bars(bars, kind="song", indices=list(range(len(vals))), series=key)
            self.ax.set_yticks(y)
            self.ax.set_yticklabels(labels, fontsize=8)
            self.ax.invert_yaxis()
            self.register_simple_song_tick_labels(y, kind="song")

        self.ax.set_title(title)
        self.ax.set_xlabel(ylabel)
        self.ax.grid(True, axis="x", alpha=0.3)


    def plot_dual_bar(self, key1, key2, title, ylabel):
        v1 = self.values(key1)
        v2 = self.values(key2)
        height = 0.42

        if self.root_mode:
            positions, labels, bar_positions, header_positions = self.grouped_song_positions()
            self.autosize_for_rows(len(positions))
            y = bar_positions
            colors1, colors2 = self.row_pair_colors(len(y))
            self.shade_album_groups()
            bars1 = self.ax.barh([i - height / 2 for i in y], v1, height=height, label=key1, color=colors1, edgecolor="black", linewidth=0.25)
            bars2 = self.ax.barh([i + height / 2 for i in y], v2, height=height, label=key2, color=colors2, edgecolor="black", linewidth=0.25)
            self.register_bars(bars1, kind="song", indices=list(range(len(v1))), series=key1)
            self.register_bars(bars2, kind="song", indices=list(range(len(v2))), series=key2)
            self.style_grouped_y_axis(positions, labels, header_positions)
        else:
            labels = self.labels()
            y = list(range(len(v1)))
            self.autosize_for_rows(len(y))
            colors1, colors2 = readable_pair_colors(len(y))
            bars1 = self.ax.barh([i - height / 2 for i in y], v1, height=height, label=key1, color=colors1, edgecolor="black", linewidth=0.25)
            bars2 = self.ax.barh([i + height / 2 for i in y], v2, height=height, label=key2, color=colors2, edgecolor="black", linewidth=0.25)
            self.register_bars(bars1, kind="song", indices=list(range(len(v1))), series=key1)
            self.register_bars(bars2, kind="song", indices=list(range(len(v2))), series=key2)
            self.ax.set_yticks(y)
            self.ax.set_yticklabels(labels, fontsize=8)
            self.ax.invert_yaxis()
            self.register_simple_song_tick_labels(y, kind="song")

        self.ax.set_title(title)
        self.ax.set_xlabel(ylabel)
        self.ax.legend()
        self.ax.grid(True, axis="x", alpha=0.3)


    def plot_pos_lines(self):
        labels = self.labels()
        x = list(range(len(labels)))

        for key, label in [
            ("noun_pct", "NOUN %"),
            ("verb_pct", "VERB %"),
            ("adj_pct", "ADJ %"),
            ("pron_pct", "PRON %"),
        ]:
            self.ax.plot(x, self.values(key), marker="o", label=label)

        self.ax.set_title("POS Distribution by Song")
        self.ax.set_ylabel("Percent")
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)

    def plot_vocabulary_growth(self):
        labels = self.labels()
        unique_values = self.values("unique_words")

        # Approximate cumulative vocabulary growth from per-song unique counts.
        # Exact growth requires song_corpus.csv. This is still useful as a quick album profile.
        cumulative = []
        total = 0.0
        for v in unique_values:
            total += v
            cumulative.append(total)

        x = list(range(len(labels)))
        self.ax.plot(x, cumulative, marker="o")
        self.ax.set_title("Approximate Vocabulary Growth")
        self.ax.set_ylabel("Cumulative unique-word mass")
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
        self.ax.grid(True, alpha=0.3)

    def plot_scatter(self, xkey, ykey, title, xlabel, ylabel):
        xs = self.values(xkey)
        ys = self.values(ykey)

        self.ax.scatter(xs, ys)

        for r, x, y in zip(self.rows, xs, ys):
            self.ax.annotate(str(int(r["index"])), (x, y), fontsize=8, xytext=(4, 4), textcoords="offset points")

        self.ax.set_title(title)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.grid(True, alpha=0.3)

    def plot_album_summary(self):
        s = album_summary(self.rows)

        names = [
            "Shannon",
            "Lexical density",
            "Repeated mass",
            "Rare density",
            "Agency ratio",
            "Action Fisher",
        ]
        vals = [
            s.get("mean_shannon", 0.0),
            s.get("mean_lexical_density", 0.0),
            s.get("mean_repeated_line_mass", 0.0),
            s.get("mean_rare_density", 0.0),
            s.get("mean_agency_ratio", 0.0),
            s.get("mean_action_fisher", 0.0),
        ]

        self.ax.bar(names, vals, color=self.plain_alternating_bar_colors(len(names)), edgecolor="black", linewidth=0.25)
        self.ax.set_title("Album Summary")
        self.ax.set_ylabel("Mean value")
        self.ax.tick_params(axis="x", rotation=35)
        self.ax.grid(True, axis="y", alpha=0.3)

    def plot_album_bar_values(self, vals, title, ylabel):
        labels = self.album_labels()
        y = list(range(len(vals)))

        bars = self.ax.barh(y, vals, color=self.album_bar_colors(), edgecolor="black", linewidth=0.25)
        self.register_bars(bars, kind="album", indices=list(range(len(vals))), series="album")
        self.ax.set_title(title)
        self.ax.set_xlabel(ylabel)
        self.ax.set_yticks(y)
        self.ax.set_yticklabels(labels, fontsize=8)
        self.ax.invert_yaxis()
        self.register_simple_song_tick_labels(y, kind="album")
        self.ax.grid(True, axis="x", alpha=0.3)
        self.add_album_legend()


    def plot_album_bar(self, key, title, ylabel):
        self.plot_album_bar_values(self.album_values(key), title, ylabel)

    def plot_album_gini_comparison(self):
        """Compare several album-level Gini coefficients in one line chart."""
        labels = self.album_labels()
        x = list(range(len(labels)))
        series = [
            ("gini_action_fisher", "Action Fisher"),
            ("gini_lexical_fisher", "Lexical Fisher"),
            ("gini_shannon", "Shannon"),
            ("gini_rare_density", "Rare density"),
        ]
        for key, label in series:
            self.ax.plot(x, self.album_values(key), marker="o", linewidth=1.5, label=label)
        self.ax.set_title("Album Gini Comparison")
        self.ax.set_ylabel("Gini coefficient")
        self.ax.set_ylim(0.0, 1.0)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)


    def plot_album_dual_bar(self, key1, key2, title, ylabel):
        labels = self.album_labels()
        v1 = self.album_values(key1)
        v2 = self.album_values(key2)
        y = list(range(len(v1)))
        height = 0.42

        colors = self.album_bar_colors()
        bars1 = self.ax.barh([i - height / 2 for i in y], v1, height=height, label=key1, color=colors, edgecolor="black", linewidth=0.25, alpha=0.95)
        bars2 = self.ax.barh([i + height / 2 for i in y], v2, height=height, label=key2, color=colors, edgecolor="black", linewidth=0.25, alpha=0.55)
        self.register_bars(bars1, kind="album", indices=list(range(len(v1))), series=key1)
        self.register_bars(bars2, kind="album", indices=list(range(len(v2))), series=key2)
        self.ax.set_title(title)
        self.ax.set_xlabel(ylabel)
        self.ax.set_yticks(y)
        self.ax.set_yticklabels(labels, fontsize=8)
        self.ax.invert_yaxis()
        self.register_simple_song_tick_labels(y, kind="album")
        self.ax.legend()
        self.ax.grid(True, axis="x", alpha=0.3)


    def plot_album_dual_line(self, key1, key2, title, ylabel):
        labels = self.album_labels()
        x = list(range(len(labels)))
        self.ax.plot(x, self.album_values(key1), marker="o", label=key1)
        self.ax.plot(x, self.album_values(key2), marker="o", label=key2)
        self.ax.set_title(title)
        self.ax.set_ylabel(ylabel)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)

    def export_csv(self):
        export_rows = self.album_rows if self.view_mode == "albums" else self.rows
        if not export_rows:
            messagebox.showwarning("No data", "Open an album folder or albums root first.")
            return

        default_name = "lyrica_parsed_metrics.csv"
        if self.folder:
            suffix = "album_scores" if self.view_mode == "albums" else "song_metrics"
            default_name = f"{self.folder.name}_{suffix}.csv"

        path = filedialog.asksaveasfilename(
            title="Save parsed metrics CSV",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if not path:
            return

        try:
            fieldnames = sorted({k for row in export_rows for k in row.keys()})
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(export_rows)

            messagebox.showinfo("Export complete", f"CSV saved:\n{path}")

        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def render_current_chart_to_figure(self, fig):
        """Render the currently selected chart into a separate Figure.

        This avoids TkAgg race conditions during PNG export.  The GUI uses its
        live Tk canvas, while export uses a fresh Agg-rendered figure.
        """
        old_fig = self.fig
        old_ax = self.ax
        old_export = self._export_mode

        try:
            self.fig = fig
            self._export_mode = True
            self.clear_plot()

            chart = self.get_selected_chart()

            if chart.startswith("ALBUMS:"):
                if not self.album_rows:
                    return
                if chart == "ALBUMS: integrated score":
                    self.plot_album_bar_values(self.integrated_album_score_values(), "Integrated Album Score", "Normalized score")
                elif chart == "ALBUMS: mean Shannon":
                    self.plot_album_bar("mean_shannon", "Mean Shannon by Album", "Mean block Shannon [bits]")
                elif chart == "ALBUMS: lexical density":
                    self.plot_album_bar("mean_lexical_density", "Lexical Density by Album", "Mean lexical density")
                elif chart == "ALBUMS: repeated line mass":
                    self.plot_album_bar("mean_repeated_line_mass", "Repeated Line Mass by Album", "Mean repeated line mass")
                elif chart == "ALBUMS: rare density":
                    self.plot_album_bar("mean_rare_density", "Rare Word Density by Album", "Mean rare density")
                elif chart == "ALBUMS: agency ratio":
                    self.plot_album_bar("mean_agency_ratio", "Agency / Noun Ratio by Album", "Mean agency / noun ratio")
                elif chart == "ALBUMS: Fisher comparison":
                    self.plot_album_dual_line("mean_lexical_fisher", "mean_action_fisher", "Lexical Fisher vs Action Fisher by Album", "Mean Fisher")
                elif chart == "ALBUMS: word totals":
                    self.plot_album_dual_bar("total_words", "total_unique_words", "Total and Unique Words by Album", "Count")
                else:
                    self.plot_album_bar_values(self.integrated_album_score_values(), "Integrated Album Score", "Normalized score")
            else:
                if not self.rows:
                    return
                if chart == "Album summary":
                    self.plot_album_summary()
                elif chart == "Mean Shannon by song":
                    self.plot_bar("mean_block_shannon", "Mean Shannon by Song", "Mean block Shannon [bits]")
                elif chart == "Lexical density by song":
                    self.plot_bar("lexical_density", "Lexical Density by Song", "Lexical density")
                elif chart == "Repeated line mass by song":
                    self.plot_bar("repeated_line_mass", "Repeated Line Mass by Song", "Repeated line mass")
                elif chart == "Rare density by song":
                    self.plot_bar("rare_density", "Rare Word Density by Song", "Rare density")
                elif chart == "Agency ratio by song":
                    self.plot_bar("agency_noun_ratio", "Agency / Noun Ratio by Song", "Agency / noun ratio")
                elif chart == "Mean lexical Fisher by song":
                    self.plot_bar("mean_lexical_fisher", "Mean Lexical Fisher by Song", "Mean lexical Fisher")
                elif chart == "Mean action Fisher by song":
                    self.plot_bar("mean_action_fisher", "Mean Action Fisher by Song", "Mean action Fisher")
                elif chart == "Vocabulary size by song":
                    self.plot_dual_bar("words", "unique_words", "Vocabulary Size by Song", "Count")
                elif chart == "POS distribution by song":
                    self.plot_pos_lines()
                elif chart == "Vocabulary growth":
                    self.plot_vocabulary_growth()
                elif chart == "Shannon vs lexical density":
                    self.plot_scatter("lexical_density", "mean_block_shannon", "Shannon vs Lexical Density", "Lexical density", "Mean block Shannon [bits]")
                else:
                    self.plot_album_summary()

            force_opaque_figure(self.fig)
            try:
                self.fig.tight_layout()
            except Exception:
                pass
        finally:
            self.fig = old_fig
            self.ax = old_ax
            self._export_mode = old_export

    def export_figure_size(self):
        """Choose a stable export size based on current chart and row count."""
        chart_name = self.get_selected_chart()
        if chart_name.startswith("ALBUMS:"):
            n = max(1, len(self.album_rows))
            return 14.0, min(28.0, max(7.0, 0.45 * n + 2.5))

        if self.root_mode and self.rows and not chart_name.startswith("ALBUMS:"):
            n_rows = len(self.grouped_song_positions()[0])
            return 16.0, min(48.0, max(8.0, 0.26 * n_rows + 2.5))

        if self.rows and chart_name in {
            "Mean Shannon by song", "Lexical density by song", "Repeated line mass by song",
            "Rare density by song", "Agency ratio by song", "Mean lexical Fisher by song",
            "Mean action Fisher by song", "Vocabulary size by song",
        }:
            n = max(1, len(self.rows))
            return 14.0, min(36.0, max(7.0, 0.32 * n + 2.5))

        return 14.0, 8.0

    def save_current_figure(self):
        if not self.rows and not self.album_rows:
            messagebox.showwarning("No data", "Open an album folder or albums root first.")
            return

        chart_name = self.get_selected_chart()
        safe = re.sub(r"[^A-Za-z0-9_]+", "_", chart_name).strip("_").lower()

        default_name = f"{safe}.png"
        if self.folder:
            default_name = f"{self.folder.name}_{safe}.png"

        path = filedialog.asksaveasfilename(
            title="Save current figure as PNG",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )

        if not path:
            return

        try:
            w, h = self.export_figure_size()
            export_fig = Figure(figsize=(w, h), dpi=100, facecolor="white")
            export_fig.patch.set_alpha(1.0)
            self.render_current_chart_to_figure(export_fig)
            save_opaque_png(export_fig, path, dpi=180)
            messagebox.showinfo("Saved", f"Figure saved:\n{path}")
        except Exception as e:
            messagebox.showerror("Save error", str(e))


def main():
    app = LyricaAlbumVisualizer()
    app.mainloop()


if __name__ == "__main__":
    main()
