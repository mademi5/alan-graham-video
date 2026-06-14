#!/usr/bin/env python3
"""
Alan Graham Video Editor — desktop GUI.

Run:
    python gui.py
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from image_zoom_reveal import (
    VideoOptions,
    generate_video,
    max_reveal_radius,
    normalize_chip_anchor,
    normalize_reveal_mode,
    resolve_crop,
    starting_radius,
)


APP_NAME = "Alan Graham Video Editor"
PREVIEW_MAX_W = 520
PREVIEW_MAX_H = 360

DEFAULT_DURATION = 10.0
DEFAULT_ZOOM_END = 7.0
DEFAULT_HOLD_END = 3.0
DEFAULT_FPS = 30
DEFAULT_REVEAL_MODE = "crop-reveal"
DEFAULT_CHIP_WIDTH_PCT = 12.0
DEFAULT_CHIP_HEIGHT_PCT = 12.0
DEFAULT_CHIP_ANCHOR = "center"
DEFAULT_RADIAL_START_PCT = 8.0
DEFAULT_BRUSH_STROKE_COUNT = 420


def _image_filetypes() -> list[tuple[str, str]]:
    # macOS Tk crashes on semicolon-separated patterns (setAllowedFileTypes).
    if sys.platform == "darwin":
        return [
            ("PNG", "*.png"),
            ("JPEG", "*.jpg"),
            ("JPEG", "*.jpeg"),
            ("WebP", "*.webp"),
            ("Bitmap", "*.bmp"),
            ("All files", "*"),
        ]
    return [
        ("Image files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
        ("All files", "*.*"),
    ]


def _video_filetypes() -> list[tuple[str, str]]:
    if sys.platform == "darwin":
        return [("MP4 video", "*.mp4")]
    return [("MP4 video", "*.mp4")]


class AlanGrahamVideoEditorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("720x680")
        self.minsize(640, 620)
        self.configure(bg="#f5f5f5")

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar(value=str(Path.cwd() / "output.mp4"))
        self.duration = tk.DoubleVar(value=DEFAULT_DURATION)
        self.zoom_end = tk.DoubleVar(value=DEFAULT_ZOOM_END)
        self.hold_end = tk.DoubleVar(value=DEFAULT_HOLD_END)
        self.fps = tk.IntVar(value=DEFAULT_FPS)
        self.reveal_mode = tk.StringVar(value=DEFAULT_REVEAL_MODE)
        self.chip_width_pct = tk.DoubleVar(value=DEFAULT_CHIP_WIDTH_PCT)
        self.chip_height_pct = tk.DoubleVar(value=DEFAULT_CHIP_HEIGHT_PCT)
        self.chip_anchor = tk.StringVar(value=DEFAULT_CHIP_ANCHOR)
        self.radial_start_pct = tk.DoubleVar(value=DEFAULT_RADIAL_START_PCT)
        self.brush_stroke_count = tk.IntVar(value=DEFAULT_BRUSH_STROKE_COUNT)
        self.status_text = tk.StringVar(value="Select an image and create your video.")
        self.progress = tk.DoubleVar(value=0.0)

        self._preview_image: ImageTk.PhotoImage | None = None
        self._source_image: Image.Image | None = None
        self._preview_scale_x = 1.0
        self._preview_scale_y = 1.0
        self._preview_display_w = 0
        self._preview_display_h = 0
        self._light_source_x: int | None = None
        self._light_source_y: int | None = None
        self.light_x_var = tk.IntVar(value=0)
        self.light_y_var = tk.IntVar(value=0)
        self._dragging_light = False
        self._suppress_light_trace = False
        self._worker: threading.Thread | None = None
        self._busy = False

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        header = tk.Label(
            self,
            text=APP_NAME,
            font=("Segoe UI", 14, "bold"),
            bg="#f5f5f5",
            fg="#222",
        )
        header.pack(anchor="w", **pad)

        subtitle = tk.Label(
            self,
            text="Crop Reveal — start from a small chip, expand to the full painting",
            font=("Segoe UI", 10),
            bg="#f5f5f5",
            fg="#555",
        )
        subtitle.pack(anchor="w", padx=12, pady=(0, 8))

        file_frame = ttk.LabelFrame(self, text="File")
        file_frame.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Entry(file_frame, textvariable=self.input_path).grid(
            row=0, column=0, sticky="ew", padx=8, pady=8
        )
        ttk.Button(file_frame, text="Select Image…", command=self._pick_input).grid(
            row=0, column=1, padx=(0, 8), pady=8
        )
        file_frame.columnconfigure(0, weight=1)

        preview_frame = ttk.LabelFrame(self, text="Preview")
        preview_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.preview_outer = tk.Frame(preview_frame, bg="#e8e8e8")
        self.preview_outer.pack(fill="both", expand=True, padx=8, pady=8)
        self.preview_canvas = tk.Canvas(
            self.preview_outer,
            bg="#e8e8e8",
            cursor="crosshair",
            highlightthickness=1,
            highlightbackground="#bbbbbb",
        )
        self.preview_canvas.bind("<Button-1>", self._on_preview_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_preview_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_preview_release)

        self.info_label = tk.Label(
            preview_frame,
            text="",
            bg="#f5f5f5",
            fg="#444",
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.info_label.pack(fill="x", padx=8, pady=(0, 8))

        crop_frame = ttk.LabelFrame(self, text="Crop Reveal")
        crop_frame.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(crop_frame, text="Chip width (%)").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        chip_w = ttk.Entry(crop_frame, textvariable=self.chip_width_pct, width=8)
        chip_w.grid(row=0, column=1, sticky="w", padx=(0, 16), pady=6)
        ttk.Label(crop_frame, text="Chip height (%)").grid(row=0, column=2, sticky="w", padx=8, pady=6)
        chip_h = ttk.Entry(crop_frame, textvariable=self.chip_height_pct, width=8)
        chip_h.grid(row=0, column=3, sticky="w", padx=(0, 8), pady=6)

        ttk.Label(crop_frame, text="Start position").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(
            crop_frame,
            textvariable=self.chip_anchor,
            values=("center", "top-left", "top-right", "bottom-left", "bottom-right"),
            state="readonly",
            width=14,
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, 8), pady=6)

        ttk.Label(
            crop_frame,
            text="Orange box in preview = starting crop chip",
            font=("Segoe UI", 9),
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))

        self.chip_width_pct.trace_add("write", lambda *_: self._refresh_preview())
        self.chip_height_pct.trace_add("write", lambda *_: self._refresh_preview())
        self.chip_anchor.trace_add("write", lambda *_: self._refresh_preview())

        self.light_frame = ttk.LabelFrame(self, text="Light Source")
        self.light_frame.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(
            self.light_frame,
            text="Click or drag on preview. Fine-tune X/Y below (pixels).",
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=8, pady=(8, 4))

        ttk.Label(self.light_frame, text="X").grid(row=1, column=0, sticky="w", padx=(8, 2), pady=4)
        self.light_x_spin = ttk.Spinbox(
            self.light_frame,
            from_=0,
            to=99999,
            textvariable=self.light_x_var,
            width=8,
            command=self._on_light_spinbox,
        )
        self.light_x_spin.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=4)

        ttk.Label(self.light_frame, text="Y").grid(row=1, column=2, sticky="w", padx=(0, 2), pady=4)
        self.light_y_spin = ttk.Spinbox(
            self.light_frame,
            from_=0,
            to=99999,
            textvariable=self.light_y_var,
            width=8,
            command=self._on_light_spinbox,
        )
        self.light_y_spin.grid(row=1, column=3, sticky="w", padx=(0, 12), pady=4)

        self.radial_label = ttk.Label(self.light_frame, text="Radial start (%)")
        self.radial_label.grid(row=1, column=4, sticky="w", padx=8, pady=4)
        self.radial_entry = ttk.Entry(self.light_frame, textvariable=self.radial_start_pct, width=8)
        self.radial_entry.grid(row=1, column=5, sticky="w", padx=(0, 8), pady=4)

        self.brush_label = ttk.Label(self.light_frame, text="Brush dabs")
        self.brush_label.grid(row=1, column=4, sticky="w", padx=8, pady=4)
        self.brush_count_spin = ttk.Spinbox(
            self.light_frame,
            from_=80,
            to=1200,
            increment=20,
            textvariable=self.brush_stroke_count,
            width=8,
        )
        self.brush_count_spin.grid(row=1, column=5, sticky="w", padx=(0, 8), pady=4)
        self.brush_label.grid_remove()
        self.brush_count_spin.grid_remove()

        self.light_pos_label = ttk.Label(self.light_frame, text="Light source: not set")
        self.light_pos_label.grid(row=2, column=0, columnspan=6, sticky="w", padx=8, pady=(0, 8))

        self.light_x_var.trace_add("write", lambda *_: self._on_light_var_changed())
        self.light_y_var.trace_add("write", lambda *_: self._on_light_var_changed())
        self.radial_start_pct.trace_add("write", lambda *_: self._refresh_preview())

        self.settings_frame = ttk.LabelFrame(self, text="Video Settings")
        self.settings_frame.pack(fill="x", padx=12, pady=(0, 8))
        settings = self.settings_frame

        fields = [
            ("Duration (sec)", self.duration),
            ("Reveal end (sec)", self.zoom_end),
            ("Hold end (sec)", self.hold_end),
            ("FPS", self.fps),
        ]
        for col, (label, var) in enumerate(fields):
            ttk.Label(settings, text=label).grid(row=0, column=col * 2, sticky="w", padx=8, pady=6)
            ttk.Entry(settings, textvariable=var, width=8).grid(
                row=0, column=col * 2 + 1, sticky="w", padx=(0, 8), pady=6
            )

        mode_row = ttk.Frame(settings)
        mode_row.grid(row=1, column=0, columnspan=8, sticky="w", padx=8, pady=(0, 4))
        ttk.Label(mode_row, text="Reveal mode").pack(side="left")
        ttk.Combobox(
            mode_row,
            textvariable=self.reveal_mode,
            values=("crop-reveal", "light-source-reveal", "brush-stroke-reveal", "zoom"),
            state="readonly",
            width=20,
        ).pack(side="left", padx=8)
        ttk.Button(mode_row, text="Reset Settings", command=self._reset_settings).pack(
            side="left", padx=(4, 0)
        )
        self.reveal_mode.trace_add("write", lambda *_: self._update_mode_ui())

        out_row = ttk.Frame(settings)
        out_row.grid(row=2, column=0, columnspan=8, sticky="ew", padx=8, pady=(0, 8))
        ttk.Label(out_row, text="Output file").pack(side="left")
        ttk.Entry(out_row, textvariable=self.output_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(out_row, text="Save As…", command=self._pick_output).pack(side="left")

        progress_frame = ttk.LabelFrame(self, text="Progress")
        progress_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(progress_frame, textvariable=self.status_text).pack(
            anchor="w", padx=8, pady=(0, 8)
        )

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        self.generate_btn = ttk.Button(
            btn_row,
            text="Create Video",
            command=self._start_generation,
        )
        self.generate_btn.pack(side="left")
        ttk.Button(btn_row, text="Exit", command=self.destroy).pack(side="right")
        self._update_mode_ui()

    def _uses_light_source(self) -> bool:
        mode = normalize_reveal_mode(self.reveal_mode.get())
        return mode in ("light-source-reveal", "brush-stroke-reveal")

    def _update_mode_ui(self) -> None:
        mode = normalize_reveal_mode(self.reveal_mode.get())
        if self._uses_light_source():
            self.light_frame.pack(fill="x", padx=12, pady=(0, 8), before=self.settings_frame)
        else:
            self.light_frame.pack_forget()

        is_radial = mode == "light-source-reveal"
        is_brush = mode == "brush-stroke-reveal"
        if is_radial:
            self.radial_label.grid()
            self.radial_entry.grid()
            self.brush_label.grid_remove()
            self.brush_count_spin.grid_remove()
        elif is_brush:
            self.radial_label.grid_remove()
            self.radial_entry.grid_remove()
            self.brush_label.grid()
            self.brush_count_spin.grid()
        self._refresh_preview()

    def _reset_settings(self) -> None:
        if self._busy:
            return

        self.duration.set(DEFAULT_DURATION)
        self.zoom_end.set(DEFAULT_ZOOM_END)
        self.hold_end.set(DEFAULT_HOLD_END)
        self.fps.set(DEFAULT_FPS)
        self.chip_width_pct.set(DEFAULT_CHIP_WIDTH_PCT)
        self.chip_height_pct.set(DEFAULT_CHIP_HEIGHT_PCT)
        self.chip_anchor.set(DEFAULT_CHIP_ANCHOR)
        self.radial_start_pct.set(DEFAULT_RADIAL_START_PCT)
        self.brush_stroke_count.set(DEFAULT_BRUSH_STROKE_COUNT)
        self.reveal_mode.set(DEFAULT_REVEAL_MODE)

        if self._source_image is not None:
            w, h = self._source_image.size
            self._set_light_position(w // 2, h // 2, update_vars=True)

        self._update_mode_ui()
        self.status_text.set("Settings reset to defaults.")

    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=_image_filetypes(),
        )
        if not path:
            return
        self.input_path.set(path)
        self._load_preview(path)

        stem = Path(path).stem
        default_out = Path(path).with_name(f"{stem}_light_reveal.mp4")
        self.output_path.set(str(default_out))

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Video",
            defaultextension=".mp4",
            filetypes=_video_filetypes(),
            initialfile=Path(self.output_path.get()).name,
        )
        if path:
            self.output_path.set(path)

    def _load_preview(self, path: str) -> None:
        try:
            img = Image.open(path).convert("RGB")
        except OSError as exc:
            messagebox.showerror("Error", f"Could not open image:\n{exc}")
            return

        self._source_image = img
        w, h = img.size
        self.light_x_spin.config(to=max(0, w - 1))
        self.light_y_spin.config(to=max(0, h - 1))
        self._set_light_position(w // 2, h // 2, update_vars=True)
        self._refresh_preview()
        self.info_label.configure(text=f"{Path(path).name}  —  {w}×{h} px")
        self.status_text.set("Image loaded. Click or drag on preview to set light source.")

    def _set_light_position(self, x: int, y: int, update_vars: bool = False) -> None:
        if self._source_image is None:
            return
        w, h = self._source_image.size
        self._light_source_x = max(0, min(int(x), w - 1))
        self._light_source_y = max(0, min(int(y), h - 1))
        if update_vars:
            self._suppress_light_trace = True
            self.light_x_var.set(self._light_source_x)
            self.light_y_var.set(self._light_source_y)
            self._suppress_light_trace = False

    def _on_light_var_changed(self) -> None:
        if self._suppress_light_trace:
            return
        if self._source_image is None:
            return
        if not self._uses_light_source():
            return
        try:
            x = int(self.light_x_var.get())
            y = int(self.light_y_var.get())
        except tk.TclError:
            return
        self._set_light_position(x, y, update_vars=False)
        self._refresh_preview()

    def _on_light_spinbox(self) -> None:
        self._on_light_var_changed()

    def _canvas_to_image(self, canvas_x: float, canvas_y: float) -> tuple[int, int] | None:
        if self._preview_display_w <= 0 or self._preview_display_h <= 0:
            return None
        if canvas_x < 0 or canvas_y < 0:
            return None
        if canvas_x >= self._preview_display_w or canvas_y >= self._preview_display_h:
            return None
        ix = int(canvas_x / self._preview_scale_x)
        iy = int(canvas_y / self._preview_scale_y)
        return ix, iy

    def _place_light_from_canvas(self, canvas_x: float, canvas_y: float) -> None:
        if not self._uses_light_source():
            return
        coords = self._canvas_to_image(canvas_x, canvas_y)
        if coords is None:
            return
        self._set_light_position(coords[0], coords[1], update_vars=True)
        self._refresh_preview()

    def _on_preview_press(self, event: tk.Event) -> None:
        if self._source_image is None:
            return
        self._dragging_light = self._uses_light_source()
        self._place_light_from_canvas(event.x, event.y)

    def _on_preview_drag(self, event: tk.Event) -> None:
        if self._dragging_light:
            self._place_light_from_canvas(event.x, event.y)

    def _on_preview_release(self, _event: tk.Event) -> None:
        self._dragging_light = False

    def _refresh_preview(self) -> None:
        if self._source_image is None:
            return

        img = self._source_image.copy()
        w, h = img.size

        try:
            chip_w_pct = float(self.chip_width_pct.get())
            chip_h_pct = float(self.chip_height_pct.get())
            radial_pct = float(self.radial_start_pct.get())
        except tk.TclError:
            return

        preview = img.copy()
        preview.thumbnail((PREVIEW_MAX_W, PREVIEW_MAX_H), Image.Resampling.LANCZOS)
        self._preview_display_w = preview.width
        self._preview_display_h = preview.height
        self._preview_scale_x = preview.width / w
        self._preview_scale_y = preview.height / h

        self._preview_image = ImageTk.PhotoImage(preview)
        self.preview_canvas.config(
            width=self._preview_display_w,
            height=self._preview_display_h,
            scrollregion=(0, 0, self._preview_display_w, self._preview_display_h),
        )
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, anchor="nw", image=self._preview_image, tags="photo")

        mode = normalize_reveal_mode(self.reveal_mode.get())

        if mode in ("light-source-reveal", "brush-stroke-reveal") and self._light_source_x is not None:
            lx, ly = self._light_source_x, self._light_source_y
            sx = lx * self._preview_scale_x
            sy = ly * self._preview_scale_y
            color = "#ffdc00" if mode == "light-source-reveal" else "#e8b4ff"
            if mode == "light-source-reveal":
                r_max = max_reveal_radius(lx, ly, w, h)
                r_start = starting_radius(w, h, chip_w_pct, chip_h_pct, radial_pct, r_max)
                sr = r_start * self._preview_scale_x
                self.preview_canvas.create_oval(
                    sx - sr, sy - sr, sx + sr, sy + sr,
                    outline=color, width=2, tags="marker",
                )
            else:
                sr = max(8, min(w, h) * 0.045 * self._preview_scale_x)
                self.preview_canvas.create_oval(
                    sx - sr, sy - sr, sx + sr, sy + sr,
                    outline=color, width=2, tags="marker",
                )
            arm = max(6, sr * 0.45)
            self.preview_canvas.create_line(
                sx - arm, sy, sx + arm, sy, fill=color, width=2, tags="marker"
            )
            self.preview_canvas.create_line(
                sx, sy - arm, sx, sy + arm, fill=color, width=2, tags="marker"
            )
            self.preview_canvas.create_oval(
                sx - 3, sy - 3, sx + 3, sy + 3, fill=color, outline="", tags="marker"
            )
            if mode == "light-source-reveal":
                r_max = max_reveal_radius(lx, ly, w, h)
                r_start = starting_radius(w, h, chip_w_pct, chip_h_pct, radial_pct, r_max)
                self.light_pos_label.configure(
                    text=f"Light source: ({lx}, {ly}) px  —  radial start {int(r_start)} px"
                )
            else:
                self.light_pos_label.configure(
                    text=f"Light source: ({lx}, {ly}) px  —  brush-stroke origin"
                )
        elif mode in ("light-source-reveal", "brush-stroke-reveal"):
            self.light_pos_label.configure(text="Light source: click or drag on preview")
        else:
            crop = resolve_crop(
                w, h, None, None, None, None, chip_w_pct, chip_h_pct, self.chip_anchor.get()
            )
            cx, cy, cw, ch = crop
            self.preview_canvas.create_rectangle(
                cx * self._preview_scale_x,
                cy * self._preview_scale_y,
                (cx + cw) * self._preview_scale_x,
                (cy + ch) * self._preview_scale_y,
                outline="#ff8c00",
                width=2,
                tags="marker",
            )

        self.preview_outer.update_idletasks()
        ow = max(self._preview_display_w, self.preview_outer.winfo_width())
        oh = max(self._preview_display_h, self.preview_outer.winfo_height())
        pos_x = max(0, (ow - self._preview_display_w) // 2)
        pos_y = max(0, (oh - self._preview_display_h) // 2)
        self.preview_canvas.place(x=pos_x, y=pos_y)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.generate_btn.configure(state=state)

    def _update_progress(self, fraction: float, message: str) -> None:
        self.progress.set(fraction * 100)
        self.status_text.set(message)

    def _on_progress(self, fraction: float, message: str) -> None:
        self.after(0, lambda: self._update_progress(fraction, message))

    def _start_generation(self) -> None:
        if self._busy:
            return

        input_path = self.input_path.get().strip()
        output_path = self.output_path.get().strip()
        if not input_path:
            messagebox.showwarning("Warning", "Please select an image file.")
            return
        if not output_path:
            messagebox.showwarning("Warning", "Please choose an output file.")
            return
        if not Path(input_path).is_file():
            messagebox.showerror("Error", "The selected image file was not found.")
            return

        try:
            chip_w_pct = float(self.chip_width_pct.get())
            chip_h_pct = float(self.chip_height_pct.get())
            if not (0 < chip_w_pct <= 100 and 0 < chip_h_pct <= 100):
                raise ValueError("Chip size must be between 0 and 100 percent")

            mode = normalize_reveal_mode(self.reveal_mode.get())
            if self._uses_light_source() and (
                self._light_source_x is None or self._light_source_y is None
            ):
                raise ValueError(
                    "Please click the preview to set the light source position."
                )

            options = VideoOptions(
                input_path=input_path,
                output_path=output_path,
                duration=float(self.duration.get()),
                hold_end=float(self.hold_end.get()),
                zoom_end=float(self.zoom_end.get()),
                crop_hold_ratio=0.0,
                fps=int(self.fps.get()),
                reveal_mode=mode,
                chip_width_pct=chip_w_pct,
                chip_height_pct=chip_h_pct,
                chip_anchor=normalize_chip_anchor(self.chip_anchor.get()),
                light_source_x=self._light_source_x,
                light_source_y=self._light_source_y,
                radial_start_pct=float(self.radial_start_pct.get()),
                brush_stroke_count=int(self.brush_stroke_count.get()),
            )
        except (tk.TclError, ValueError) as exc:
            messagebox.showerror("Error", f"Invalid setting value:\n{exc}")
            return

        self._set_busy(True)
        self.progress.set(0)
        self.status_text.set("Starting…")

        def worker() -> None:
            try:
                result = generate_video(options, progress_callback=self._on_progress)
                self.after(0, lambda: self._on_success(result))
            except Exception as exc:
                self.after(0, lambda: self._on_error(str(exc)))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _on_success(self, output_path: str) -> None:
        self._set_busy(False)
        self.progress.set(100)
        self.status_text.set(f"Video ready: {output_path}")
        self.bell()
        if messagebox.askyesno(
            "Video Ready",
            f"Video created successfully:\n\n{output_path}\n\nOpen the folder?",
        ):
            try:
                os.startfile(str(Path(output_path).parent))  # type: ignore[attr-defined]
            except OSError:
                pass

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.progress.set(0)
        self.status_text.set("An error occurred.")
        messagebox.showerror("Error", message)


def main() -> None:
    app = AlanGrahamVideoEditorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
