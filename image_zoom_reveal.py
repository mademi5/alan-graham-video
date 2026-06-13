#!/usr/bin/env python3
"""
Crop Reveal: crop the painting to a small chip, then reveal the full image.

Example usage:
    python image_zoom_reveal.py --input photo.jpg --output reveal.mp4
    python image_zoom_reveal.py --input photo.png --reveal-mode crop-reveal \\
        --chip-width-pct 12 --chip-height-pct 12 --duration 10 --zoom-end 7 --hold-end 3
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np
from PIL import Image

try:
    from moviepy import VideoClip
except ImportError:
    from moviepy.editor import VideoClip  # type: ignore[no-redef]

try:
    from proglog import ProgressBarLogger
except ImportError:
    ProgressBarLogger = None  # type: ignore[misc, assignment]


@dataclass
class VideoOptions:
    input_path: str
    output_path: str = "output.mp4"
    crop_x: int | None = None
    crop_y: int | None = None
    crop_w: int | None = None
    crop_h: int | None = None
    duration: float = 10.0
    hold_end: float = 3.0
    zoom_end: float | None = None
    crop_hold_ratio: float = 0.0
    fps: int = 30
    reveal_mode: str = "crop-reveal"
    chip_width_pct: float | None = None
    chip_height_pct: float | None = None
    chip_anchor: str = "center"
    light_source_x: int | None = None
    light_source_y: int | None = None
    radial_start_pct: float = 8.0
    brush_stroke_count: int = 420


VALID_REVEAL_MODES = ("crop-reveal", "zoom", "light-source-reveal", "brush-stroke-reveal")
VALID_CHIP_ANCHORS = ("center", "top-left", "top-right", "bottom-left", "bottom-right")


def normalize_chip_anchor(anchor: str) -> str:
    normalized = anchor.lower().replace("_", "-").strip()
    aliases = {
        "middle": "center",
        "centre": "center",
        "tl": "top-left",
        "tr": "top-right",
        "bl": "bottom-left",
        "br": "bottom-right",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in VALID_CHIP_ANCHORS:
        raise ValueError(
            "Chip anchor must be one of: center, top-left, top-right, bottom-left, bottom-right"
        )
    return normalized


def chip_origin(
    img_w: int,
    img_h: int,
    width: int,
    height: int,
    anchor: str,
) -> Tuple[int, int]:
    anchor = normalize_chip_anchor(anchor)
    if anchor == "center":
        return (img_w - width) // 2, (img_h - height) // 2
    if anchor == "top-left":
        return 0, 0
    if anchor == "top-right":
        return img_w - width, 0
    if anchor == "bottom-left":
        return 0, img_h - height
    return img_w - width, img_h - height


def normalize_reveal_mode(mode: str) -> str:
    normalized = mode.lower().replace("_", "-")
    if normalized in ("uncrop", "crop-reveal"):
        return "crop-reveal"
    if normalized in ("light-source", "light-source-reveal", "radial-reveal"):
        return "light-source-reveal"
    if normalized in ("brush-stroke", "brush-stroke-reveal", "cinematic-brush"):
        return "brush-stroke-reveal"
    if normalized == "zoom":
        return "zoom"
    raise ValueError(
        "Reveal mode must be 'crop-reveal', 'light-source-reveal', "
        "'brush-stroke-reveal', or 'zoom'"
    )


ProgressCallback = Callable[[float, str], None]


def ease_in_out(t: float) -> float:
    """Smooth ease-in-out curve (smoothstep)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an uncrop reveal video from a small image chip to the full image."
    )
    parser.add_argument("--input", required=True, help="Path to source image (jpg or png)")
    parser.add_argument("--output", default="output.mp4", help="Output MP4 path (default: output.mp4)")
    parser.add_argument("--crop-x", type=int, default=None, help="Crop region top-left X (default: centered)")
    parser.add_argument("--crop-y", type=int, default=None, help="Crop region top-left Y (default: centered)")
    parser.add_argument("--crop-w", type=int, default=None, help="Crop width (default: ~20%% of image width)")
    parser.add_argument("--crop-h", type=int, default=None, help="Crop height (default: ~20%% of image height)")
    parser.add_argument("--duration", type=float, default=5.0, help="Total video duration in seconds (default: 5)")
    parser.add_argument(
        "--hold-end",
        type=float,
        default=1.5,
        help="Seconds to hold the full image at the end (default: 1.5)",
    )
    parser.add_argument(
        "--zoom-end",
        type=float,
        default=None,
        help="Second at which zoom completes (default: duration - hold-end)",
    )
    parser.add_argument(
        "--crop-hold-ratio",
        type=float,
        default=0.30,
        help="Fraction of zoom time to hold on crop before transitioning (0 = proportional zoom)",
    )
    parser.add_argument(
        "--reveal-mode",
        choices=("crop-reveal", "uncrop", "zoom", "light-source-reveal", "brush-stroke-reveal"),
        default="crop-reveal",
        help="crop-reveal | light-source-reveal | brush-stroke-reveal | zoom",
    )
    parser.add_argument(
        "--chip-width-pct",
        type=float,
        default=None,
        help="Crop chip width as %% of image width (default: 12)",
    )
    parser.add_argument(
        "--chip-height-pct",
        type=float,
        default=None,
        help="Crop chip height as %% of image height (default: 12)",
    )
    parser.add_argument(
        "--chip-anchor",
        choices=VALID_CHIP_ANCHORS,
        default="center",
        help="Starting position of the crop chip (default: center)",
    )
    parser.add_argument(
        "--light-x",
        type=int,
        default=None,
        help="Light source X (pixels) for light-source-reveal",
    )
    parser.add_argument(
        "--light-y",
        type=int,
        default=None,
        help="Light source Y (pixels) for light-source-reveal",
    )
    parser.add_argument(
        "--radial-start-pct",
        type=float,
        default=8.0,
        help="Starting radial reveal size as %% of max radius (default: 8)",
    )
    parser.add_argument(
        "--brush-stroke-count",
        type=int,
        default=420,
        help="Number of brush dabs for brush-stroke-reveal (default: 420)",
    )
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30)")
    return parser.parse_args()


def resolve_crop(
    img_w: int,
    img_h: int,
    crop_x: int | None,
    crop_y: int | None,
    crop_w: int | None,
    crop_h: int | None,
    chip_width_pct: float | None = None,
    chip_height_pct: float | None = None,
    chip_anchor: str = "center",
) -> Tuple[int, int, int, int]:
    if crop_w is None and chip_width_pct is not None:
        width = max(1, int(round(img_w * chip_width_pct / 100.0)))
    else:
        width = crop_w if crop_w is not None else max(1, int(round(img_w * 0.12)))

    if crop_h is None and chip_height_pct is not None:
        height = max(1, int(round(img_h * chip_height_pct / 100.0)))
    else:
        height = crop_h if crop_h is not None else max(1, int(round(img_h * 0.12)))

    width = min(width, img_w)
    height = min(height, img_h)

    origin_x, origin_y = chip_origin(img_w, img_h, width, height, chip_anchor)
    x = crop_x if crop_x is not None else origin_x
    y = crop_y if crop_y is not None else origin_y

    x = max(0, min(x, img_w - width))
    y = max(0, min(y, img_h - height))

    return x, y, width, height


def visible_rect_at_time(
    t: float,
    zoom_end: float,
    hold_start: float,
    crop_hold_ratio: float,
    crop: Tuple[int, int, int, int],
    img_w: int,
    img_h: int,
) -> Tuple[int, int, int, int]:
    """Return the visible source-image rectangle for time t."""
    if t >= hold_start - 1e-9:
        return 0, 0, img_w, img_h

    crop_x, crop_y, crop_w, crop_h = crop
    phase1_end = zoom_end * max(0.0, min(crop_hold_ratio, 1.0))

    if t <= phase1_end:
        progress = 0.0
    else:
        span = zoom_end - phase1_end
        raw = (t - phase1_end) / span if span > 0 else 1.0
        progress = ease_in_out(raw)

    if progress >= 1.0:
        return 0, 0, img_w, img_h

    x = crop_x + (0 - crop_x) * progress
    y = crop_y + (0 - crop_y) * progress
    w = crop_w + (img_w - crop_w) * progress
    h = crop_h + (img_h - crop_h) * progress

    return int(round(x)), int(round(y)), int(round(w)), int(round(h))


def reveal_progress_at_time(
    t: float,
    reveal_end: float,
    hold_start: float,
    hold_ratio: float,
) -> float:
    if t >= hold_start - 1e-9:
        return 1.0

    phase1_end = reveal_end * max(0.0, min(hold_ratio, 1.0))
    if t <= phase1_end:
        return 0.0

    span = reveal_end - phase1_end
    raw = (t - phase1_end) / span if span > 0 else 1.0
    return ease_in_out(raw)


def max_reveal_radius(cx: float, cy: float, img_w: int, img_h: int) -> float:
    corners = ((0, 0), (img_w, 0), (0, img_h), (img_w, img_h))
    return max(math.hypot(cx - x, cy - y) for x, y in corners) + 2.0


def resolve_light_source(
    img_w: int,
    img_h: int,
    light_x: int | None,
    light_y: int | None,
) -> Tuple[int, int]:
    if light_x is None or light_y is None:
        raise ValueError("Light source position is required for Light Source Reveal")
    x = max(0, min(int(light_x), img_w - 1))
    y = max(0, min(int(light_y), img_h - 1))
    return x, y


def starting_radius(
    img_w: int,
    img_h: int,
    chip_width_pct: float | None,
    chip_height_pct: float | None,
    radial_start_pct: float,
    r_max: float,
) -> float:
    r_pct = r_max * max(2.0, min(radial_start_pct, 50.0)) / 100.0
    if chip_width_pct is not None and chip_height_pct is not None:
        cw = img_w * chip_width_pct / 100.0
        ch = img_h * chip_height_pct / 100.0
        r_chip = 0.5 * math.hypot(cw, ch)
        return max(6.0, min(r_chip, r_pct))
    return max(6.0, r_pct)


def build_distance_map(img_w: int, img_h: int, cx: int, cy: int) -> np.ndarray:
    xs = np.arange(img_w, dtype=np.float32)
    ys = np.arange(img_h, dtype=np.float32)
    dx = xs - cx
    dy = ys - cy
    return np.hypot(dx[np.newaxis, :], dy[:, np.newaxis])


def render_frame_light_source_reveal(
    source: np.ndarray,
    dist_map: np.ndarray,
    radius: float,
    r_max: float,
) -> np.ndarray:
    if radius >= r_max - 0.5:
        return pad_frame_to_even(source)

    feather = max(6.0, radius * 0.12)
    alpha = np.clip((radius - dist_map) / feather, 0.0, 1.0)
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)

    frame = (source.astype(np.float32) * alpha[..., np.newaxis]).astype(np.uint8)
    return pad_frame_to_even(frame)


def even_dimensions(width: int, height: int) -> Tuple[int, int]:
    """H.264 requires even width and height."""
    return width + width % 2, height + height % 2


def pad_frame_to_even(frame: np.ndarray) -> np.ndarray:
    """Pad frame by 1px on right/bottom if needed for H.264 encoding."""
    h, w = frame.shape[:2]
    pad_w = w % 2
    pad_h = h % 2
    if pad_w == 0 and pad_h == 0:
        return frame
    return np.pad(frame, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")


def render_frame_zoom(source: Image.Image, rect: Tuple[int, int, int, int], out_w: int, out_h: int) -> np.ndarray:
    """Scale the visible region up to fill the output frame."""
    x, y, w, h = rect

    if x == 0 and y == 0 and w == source.width and h == source.height:
        return pad_frame_to_even(np.asarray(source))

    x = max(0, min(x, source.width - 1))
    y = max(0, min(y, source.height - 1))
    w = max(1, min(w, source.width - x))
    h = max(1, min(h, source.height - y))

    region = source.crop((x, y, x + w, y + h))
    frame = region.resize((out_w, out_h), Image.Resampling.LANCZOS)
    return pad_frame_to_even(np.array(frame))


def render_frame_crop_reveal(
    source: Image.Image, rect: Tuple[int, int, int, int], out_w: int, out_h: int
) -> np.ndarray:
    """Crop-reveal: place the chip at 1:1 scale, then expand the crop window."""
    x, y, w, h = rect

    if x == 0 and y == 0 and w == source.width and h == source.height:
        return pad_frame_to_even(np.asarray(source))

    x = max(0, min(x, source.width - 1))
    y = max(0, min(y, source.height - 1))
    w = max(1, min(w, source.width - x))
    h = max(1, min(h, source.height - y))

    canvas = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    region = source.crop((x, y, x + w, y + h))
    canvas.paste(region, (x, y))
    return pad_frame_to_even(np.array(canvas))


def render_frame(
    source: Image.Image,
    rect: Tuple[int, int, int, int],
    out_w: int,
    out_h: int,
    mode: str = "crop-reveal",
) -> np.ndarray:
    mode = normalize_reveal_mode(mode)
    if mode == "zoom":
        return render_frame_zoom(source, rect, out_w, out_h)
    return render_frame_crop_reveal(source, rect, out_w, out_h)


def validate_options(options: VideoOptions) -> tuple[float, float, float]:
    if options.duration <= 0:
        raise ValueError("Duration must be greater than 0")
    if options.hold_end <= 0:
        raise ValueError("Hold end must be greater than 0")
    if options.hold_end >= options.duration:
        raise ValueError("Hold end must be less than total duration")
    if not 0.0 <= options.crop_hold_ratio <= 1.0:
        raise ValueError("Crop hold ratio must be between 0 and 1")
    if options.fps <= 0:
        raise ValueError("FPS must be greater than 0")
    mode = normalize_reveal_mode(options.reveal_mode)
    normalize_chip_anchor(options.chip_anchor)
    if mode in ("light-source-reveal", "brush-stroke-reveal"):
        if options.light_source_x is None or options.light_source_y is None:
            raise ValueError("Light source position is required for this reveal mode")
    if mode == "light-source-reveal" and not 0.0 < options.radial_start_pct <= 50.0:
        raise ValueError("Radial start percent must be between 0 and 50")
    if mode == "brush-stroke-reveal" and options.brush_stroke_count < 50:
        raise ValueError("Brush stroke count must be at least 50")

    zoom_end = options.zoom_end if options.zoom_end is not None else options.duration - options.hold_end
    if zoom_end <= 0 or zoom_end >= options.duration:
        raise ValueError("Invalid zoom end time")

    return options.duration, options.hold_end, zoom_end


def make_progress_logger(callback: ProgressCallback | None):
    if callback is None or ProgressBarLogger is None:
        return None

    class _GuiProgressLogger(ProgressBarLogger):
        def bars_callback(self, bar, attr, value, old_value=None):
            if bar != "t" or attr != "index":
                return
            total = self.bars.get(bar, {}).get("total")
            if total:
                percent = min(1.0, max(0.0, value / total))
                callback(percent, f"Rendering frames… {int(percent * 100)}%")

    return _GuiProgressLogger()


def generate_video(
    options: VideoOptions,
    progress_callback: ProgressCallback | None = None,
) -> str:
    try:
        source = Image.open(options.input_path).convert("RGB")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {options.input_path}") from exc
    except OSError as exc:
        raise OSError(f"Could not open image: {exc}") from exc

    img_w, img_h = source.size
    mode = normalize_reveal_mode(options.reveal_mode)
    duration, hold_end, zoom_end = validate_options(options)
    hold_start = zoom_end
    source_arr = np.asarray(source)

    if progress_callback:
        progress_callback(0.02, "Preparing video…")

    if mode == "light-source-reveal":
        lx, ly = resolve_light_source(
            img_w, img_h, options.light_source_x, options.light_source_y
        )
        r_max = max_reveal_radius(lx, ly, img_w, img_h)
        r_start = starting_radius(
            img_w,
            img_h,
            options.chip_width_pct,
            options.chip_height_pct,
            options.radial_start_pct,
            r_max,
        )
        dist_map = build_distance_map(img_w, img_h, lx, ly)

        def make_frame(t: float) -> np.ndarray:
            progress = reveal_progress_at_time(
                t, zoom_end, hold_start, options.crop_hold_ratio
            )
            radius = r_start + (r_max - r_start) * progress
            return render_frame_light_source_reveal(source_arr, dist_map, radius, r_max)

    elif mode == "brush-stroke-reveal":
        from brush_stroke_reveal import BrushStrokeEngine, render_brush_stroke_frame

        lx, ly = resolve_light_source(
            img_w, img_h, options.light_source_x, options.light_source_y
        )
        if progress_callback:
            progress_callback(0.05, "Generating brush strokes…")
        engine = BrushStrokeEngine(
            img_w, img_h, lx, ly, dab_count=options.brush_stroke_count
        )
        pullback_span = max(hold_end * 0.55, 0.5)

        def make_frame(t: float) -> np.ndarray:
            if t >= hold_start:
                reveal_p = 1.0
                pb_t = (t - hold_start) / pullback_span if pullback_span > 0 else 1.0
                pullback = ease_in_out(min(1.0, pb_t))
            else:
                reveal_p = reveal_progress_at_time(
                    t, zoom_end, hold_start, options.crop_hold_ratio
                )
                pullback = 0.0
            return render_brush_stroke_frame(
                source_arr, engine, lx, ly, t, reveal_p, pullback
            )

    else:
        crop = resolve_crop(
            img_w,
            img_h,
            options.crop_x,
            options.crop_y,
            options.crop_w,
            options.crop_h,
            options.chip_width_pct,
            options.chip_height_pct,
            options.chip_anchor,
        )

        def make_frame(t: float) -> np.ndarray:
            rect = visible_rect_at_time(
                t, zoom_end, hold_start, options.crop_hold_ratio, crop, img_w, img_h
            )
            return render_frame(source, rect, img_w, img_h, mode)

    clip = VideoClip(make_frame, duration=duration)
    clip = clip.with_fps(options.fps) if hasattr(clip, "with_fps") else clip.set_fps(options.fps)

    write_kwargs = {
        "codec": "libx264",
        "fps": options.fps,
        "audio": False,
        "preset": "medium",
        "ffmpeg_params": ["-pix_fmt", "yuv420p"],
        "logger": make_progress_logger(progress_callback),
    }

    try:
        clip.write_videofile(options.output_path, **write_kwargs)
    finally:
        clip.close()

    if progress_callback:
        progress_callback(1.0, "Complete")

    return options.output_path


def main() -> int:
    args = parse_args()

    options = VideoOptions(
        input_path=args.input,
        output_path=args.output,
        crop_x=args.crop_x,
        crop_y=args.crop_y,
        crop_w=args.crop_w,
        crop_h=args.crop_h,
        duration=args.duration,
        hold_end=args.hold_end,
        zoom_end=args.zoom_end,
        crop_hold_ratio=args.crop_hold_ratio,
        fps=args.fps,
        reveal_mode=normalize_reveal_mode(args.reveal_mode),
        chip_width_pct=args.chip_width_pct,
        chip_height_pct=args.chip_height_pct,
        chip_anchor=normalize_chip_anchor(args.chip_anchor),
        light_source_x=args.light_x,
        light_source_y=args.light_y,
        radial_start_pct=args.radial_start_pct,
        brush_stroke_count=args.brush_stroke_count,
    )

    try:
        output = generate_video(options)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: failed to write video: {exc}", file=sys.stderr)
        return 1

    try:
        source = Image.open(options.input_path)
        img_w, img_h = source.size
        enc_w, enc_h = even_dimensions(img_w, img_h)
        duration, hold_end, zoom_end = validate_options(options)
        hold_start = zoom_end
        size_note = f"{enc_w}x{enc_h}" if (enc_w, enc_h) != (img_w, img_h) else f"{img_w}x{img_h}"
        print(
            f"Saved {output} ({size_note}, {duration}s @ {options.fps} fps, "
            f"{normalize_reveal_mode(options.reveal_mode)} 0-{zoom_end:.1f}s, "
            f"hold {hold_start:.1f}-{duration:.1f}s)"
        )
    except OSError:
        print(f"Saved {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
