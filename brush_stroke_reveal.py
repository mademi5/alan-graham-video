"""Cinematic brush-stroke reveal — organic hand-painted animation from a light source."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from PIL import Image

from image_zoom_reveal import ease_in_out, pad_frame_to_even


@dataclass
class BrushDab:
    x: float
    y: float
    radius: float
    angle: float
    alpha: float
    t_start: float
    t_end: float


def _smooth_noise(h: int, w: int, rng: np.random.Generator, scale: int = 8) -> np.ndarray:
    coarse_h = max(2, h // scale)
    coarse_w = max(2, w // scale)
    coarse = rng.random((coarse_h, coarse_w), dtype=np.float32)
    img = Image.fromarray((coarse * 255).astype(np.uint8), mode="L")
    img = img.resize((w, h), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.float32) / 255.0


def _make_brush_kernel(radius: float, angle: float, rng: np.random.Generator) -> np.ndarray:
    size = max(8, int(radius * 2.6))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = (size - 1) / 2.0
    rx = radius * rng.uniform(0.75, 1.35)
    ry = radius * rng.uniform(0.55, 1.15)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    dx = xx - cx
    dy = yy - cy
    rx_p = dx * cos_a + dy * sin_a
    ry_p = -dx * sin_a + dy * cos_a
    dist = (rx_p / max(rx, 1e-3)) ** 2 + (ry_p / max(ry, 1e-3)) ** 2
    kernel = np.clip(1.0 - dist, 0.0, 1.0)
    kernel = kernel ** rng.uniform(1.2, 2.4)
    edge = rng.random((size, size), dtype=np.float32) * 0.18
    kernel = np.clip(kernel + edge * kernel, 0.0, 1.0)
    return kernel


def generate_brush_dabs(
    img_w: int,
    img_h: int,
    light_x: int,
    light_y: int,
    count: int = 420,
    seed: int = 42,
) -> List[BrushDab]:
    rng = np.random.default_rng(seed)
    dabs: List[BrushDab] = []
    span = max(img_w, img_h)
    base_r = max(6.0, span * 0.012)

    for i in range(count):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(0, span * 0.55) ** rng.uniform(0.65, 1.0)
        x = light_x + math.cos(angle) * dist + rng.normal(0, base_r * 0.35)
        y = light_y + math.sin(angle) * dist + rng.normal(0, base_r * 0.35)

        # Strokes closer to light appear earlier; distant strokes trail in organically.
        norm_dist = min(1.0, dist / (span * 0.62))
        t_start = 0.06 + norm_dist * 0.52 + rng.uniform(0, 0.18)
        t_end = min(0.98, t_start + rng.uniform(0.08, 0.28))

        radius = base_r * rng.uniform(0.55, 2.1) * (1.0 + norm_dist * 0.35)
        dab_angle = rng.uniform(0, math.pi)
        alpha = rng.uniform(0.55, 1.0)

        # Chain dabs for stroke-like trails
        steps = rng.integers(2, 7)
        for s in range(steps):
            frac = s / max(steps - 1, 1)
            sx = x + math.cos(dab_angle) * radius * 0.9 * s + rng.normal(0, 1.5)
            sy = y + math.sin(dab_angle) * radius * 0.9 * s + rng.normal(0, 1.5)
            sx = float(np.clip(sx, 0, img_w - 1))
            sy = float(np.clip(sy, 0, img_h - 1))
            st = t_start + frac * (t_end - t_start) * 0.85
            en = min(0.99, st + 0.12)
            dabs.append(
                BrushDab(
                    x=sx,
                    y=sy,
                    radius=radius * rng.uniform(0.75, 1.15),
                    angle=dab_angle + rng.uniform(-0.6, 0.6),
                    alpha=alpha,
                    t_start=st,
                    t_end=en,
                )
            )

    dabs.sort(key=lambda d: d.t_start)
    return dabs


def _stamp_kernel(
    mask: np.ndarray,
    kernel: np.ndarray,
    cx: float,
    cy: float,
    strength: float,
) -> None:
    h, w = mask.shape
    kh, kw = kernel.shape
    x0 = int(round(cx - kw / 2))
    y0 = int(round(cy - kh / 2))
    x1 = x0 + kw
    y1 = y0 + kh

    sx0 = max(0, -x0)
    sy0 = max(0, -y0)
    sx1 = kw - max(0, x1 - w)
    sy1 = kh - max(0, y1 - h)

    dx0 = max(0, x0)
    dy0 = max(0, y0)
    dx1 = min(w, x1)
    dy1 = min(h, y1)

    if dx0 >= dx1 or dy0 >= dy1:
        return

    patch = kernel[sy0:sy1, sx0:sx1] * strength
    region = mask[dy0:dy1, dx0:dx1]
    np.maximum(region, patch, out=region)


class BrushStrokeEngine:
    """Builds organic reveal masks from procedural brush dabs."""

    def __init__(
        self,
        img_w: int,
        img_h: int,
        light_x: int,
        light_y: int,
        dab_count: int = 420,
        mask_scale: float | None = None,
        seed: int = 42,
    ) -> None:
        self.img_w = img_w
        self.img_h = img_h
        self.light_x = light_x
        self.light_y = light_y
        self.rng = np.random.default_rng(seed)

        if mask_scale is None:
            mask_scale = max(0.35, min(1.0, 960.0 / max(img_w, img_h)))
        self.mask_scale = mask_scale
        self.mw = max(32, int(round(img_w * mask_scale)))
        self.mh = max(32, int(round(img_h * mask_scale)))
        self.lx = light_x * mask_scale
        self.ly = light_y * mask_scale

        self.dabs = generate_brush_dabs(self.mw, self.mh, int(self.lx), int(self.ly), dab_count, seed)
        self.noise = _smooth_noise(self.mh, self.mw, self.rng, scale=10)
        self._kernels: dict[tuple[int, int], np.ndarray] = {}

    def _kernel(self, dab: BrushDab) -> np.ndarray:
        key = (int(dab.radius * 10), int(dab.angle * 100) % 628)
        if key not in self._kernels:
            self._kernels[key] = _make_brush_kernel(dab.radius, dab.angle, self.rng)
        return self._kernels[key]

    def mask_at_progress(self, progress: float) -> np.ndarray:
        progress = ease_in_out(max(0.0, min(1.0, progress)))
        mask = np.zeros((self.mh, self.mw), dtype=np.float32)

        for dab in self.dabs:
            if progress <= dab.t_start:
                continue
            local = (progress - dab.t_start) / max(dab.t_end - dab.t_start, 1e-6)
            local = ease_in_out(min(1.0, local))
            if local <= 0:
                continue
            _stamp_kernel(mask, self._kernel(dab), dab.x, dab.y, dab.alpha * local)

        # Organic fill: noise-threshold expands coverage without a hard radial edge.
        fill_level = ease_in_out(max(0.0, (progress - 0.18) / 0.82))
        if fill_level > 0:
            dist = np.hypot(
                np.arange(self.mw, dtype=np.float32)[np.newaxis, :] - self.lx,
                np.arange(self.mh, dtype=np.float32)[:, np.newaxis] - self.ly,
            )
            dist_norm = dist / (dist.max() + 1e-6)
            threshold = fill_level * 1.08 + self.noise * (0.22 - fill_level * 0.12)
            organic = (dist_norm + self.noise * 0.38) < threshold
            mask = np.maximum(mask, organic.astype(np.float32) * fill_level)

        if progress >= 0.995:
            mask.fill(1.0)

        return mask

    def upscale_mask(self, mask: np.ndarray) -> np.ndarray:
        if self.mask_scale >= 0.999:
            return mask
        img = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), mode="L")
        img = img.resize((self.img_w, self.img_h), Image.Resampling.BILINEAR)
        return np.asarray(img, dtype=np.float32) / 255.0


def light_glow_layer(
    source: np.ndarray,
    light_x: int,
    light_y: int,
    t: float,
    pulse_hz: float = 0.65,
    base_radius: float | None = None,
) -> np.ndarray:
    h, w = source.shape[:2]
    if base_radius is None:
        base_radius = max(12.0, min(w, h) * 0.045)

    pulse = 0.82 + 0.18 * math.sin(t * 2 * math.pi * pulse_hz)
    radius = base_radius * pulse

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.hypot(xx - light_x, yy - light_y)
    glow = np.clip(1.0 - dist / max(radius, 1.0), 0.0, 1.0)
    glow = glow ** 2.2

    sample_r = max(2, int(base_radius * 0.35))
    x0 = max(0, light_x - sample_r)
    y0 = max(0, light_y - sample_r)
    x1 = min(w, light_x + sample_r)
    y1 = min(h, light_y + sample_r)
    core = source[y0:y1, x0:x1].astype(np.float32).mean(axis=(0, 1))
    warm = core * 1.08 + np.array([18.0, 12.0, 4.0], dtype=np.float32)

    glow_rgb = glow[..., np.newaxis] * warm[np.newaxis, np.newaxis, :]
    return glow_rgb.astype(np.float32)


def apply_pullback(source: np.ndarray, amount: float) -> np.ndarray:
    """Subtle gallery pull-back: scale from >1 down to 1.0 (amount 0→1)."""
    if amount <= 0:
        return source

    h, w = source.shape[:2]
    scale = 1.0 + (1.0 - ease_in_out(amount)) * 0.045
    new_w = max(w, int(round(w * scale)))
    new_h = max(h, int(round(h * scale)))

    img = Image.fromarray(source)
    enlarged = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    cropped = enlarged.crop((left, top, left + w, top + h))
    return np.asarray(cropped)


def render_brush_stroke_frame(
    source: np.ndarray,
    engine: BrushStrokeEngine,
    light_x: int,
    light_y: int,
    t: float,
    reveal_progress: float,
    pullback_amount: float,
) -> np.ndarray:
    h, w = source.shape[:2]

    if reveal_progress >= 1.0 and pullback_amount <= 0:
        return pad_frame_to_even(source)

    mask_small = engine.mask_at_progress(reveal_progress)
    mask = engine.upscale_mask(mask_small)

    if reveal_progress >= 1.0:
        frame = source.copy()
    else:
        dark = np.zeros_like(source, dtype=np.float32)
        painted = source.astype(np.float32) * mask[..., np.newaxis]
        glow = light_glow_layer(source, light_x, light_y, t)
        glow_strength = max(0.15, 1.0 - reveal_progress * 0.92)
        frame = np.clip(dark + painted + glow * glow_strength, 0, 255).astype(np.uint8)

    if pullback_amount > 0:
        frame = apply_pullback(frame, pullback_amount)

    return pad_frame_to_even(frame)
