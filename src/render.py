"""Genera un video vertical 1080x1920 de texto animado a partir de una idea de la cola."""
from __future__ import annotations

import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
MUSIC = ROOT / "assets" / "music"


# ── utilidades ──────────────────────────────────────────────
def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size)


def wrap(text: str, fnt, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if fnt.getlength(test) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, weight: str, max_w: int, max_h: int, start: int, min_size=48):
    size = start
    while size > min_size:
        f = font(weight, size)
        lines = wrap(text, f, max_w)
        lh = int(size * 1.18)
        if lh * len(lines) <= max_h and all(f.getlength(l) <= max_w for l in lines):
            return f, lines, lh
        size -= 4
    f = font(weight, min_size)
    return f, wrap(text, f, max_w), int(min_size * 1.18)


def text_layer(W, H, lines, fnt, lh, color, highlight=None, y_center=None):
    """Capa RGBA con texto centrado + sombra suave."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    total = lh * len(lines)
    y = (y_center if y_center is not None else H // 2) - total // 2
    for line in lines:
        x = (W - fnt.getlength(line)) // 2
        ds.text((x + 4, y + 6), line, font=fnt, fill=(0, 0, 0, 150))
        d.text((x, y), line, font=fnt, fill=color + (255,))
        y += lh
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    return Image.alpha_composite(shadow, layer)


def gradient(W, H, top, bottom) -> np.ndarray:
    t = np.linspace(0, 1, H)[:, None, None]
    a, b = np.array(top, float), np.array(bottom, float)
    return np.broadcast_to(a * (1 - t) + b * t, (H, W, 3)).astype(np.float32)


def blob(size, color) -> np.ndarray:
    img = Image.new("L", (size, size), 0)
    ImageDraw.Draw(img).ellipse((size * 0.3, size * 0.3, size * 0.7, size * 0.7), fill=255)
    img = img.filter(ImageFilter.GaussianBlur(size * 0.09))
    a = np.asarray(img, np.float32)[..., None] / 255.0 * 0.35
    return a, np.array(color, np.float32)


# ── audio ───────────────────────────────────────────────────
def music_input(item_id: str, duration: float, volume: float) -> list[str]:
    tracks = sorted(p for p in MUSIC.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"})
    if tracks:
        track = random.Random(item_id).choice(tracks)
        return ["-stream_loop", "-1", "-i", str(track)]
    # Pad sintético (Am – F – C – G) con pulso suave: no requiere archivos ni licencias
    chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (130.81, 196.0, 261.63), (196.0, 246.94, 293.66)]
    parts = []
    for i, ch in enumerate(chords):
        tone = "+".join(f"sin(2*PI*{f}*t)" for f in ch)
        parts.append(f"eq(floor(mod(t,16)/4),{i})*({tone})")
    pad = "(" + "+".join(parts) + ")*0.12*(0.75+0.25*sin(2*PI*0.5*t))"
    kick = "0.5*sin(2*PI*55*t)*exp(-mod(t,0.5)*14)"
    hat = "0.04*(random(0)-0.5)*exp(-mod(t+0.25,0.5)*40)"
    expr = f"{pad}+{kick}+{hat}"
    return ["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={duration:.2f}"]


# ── render ──────────────────────────────────────────────────
def render(item: dict, cfg: dict, out_path: Path) -> Path:
    st = cfg["style"]
    W, H, FPS = st["width"], st["height"], st["fps"]
    accent, txt, muted = hex_rgb(st["accent"]), hex_rgb(st["text"]), hex_rgb(st["muted"])
    margin = 110
    max_w = W - margin * 2

    # Escenas: (tipo, texto, duración)
    scenes = [("hook", item["hook"], st["hook_seconds"])]
    scenes += [("point", p, st["point_seconds"]) for p in item["points"]]
    scenes += [("cta", item.get("cta", "Sígueme para más"), st["cta_seconds"])]
    total = sum(s[2] for s in scenes)
    n_frames = int(total * FPS)
    n_points = len(item["points"])

    # Pre-render de capas de texto por escena
    layers = []
    for kind, text, _ in scenes:
        if kind == "hook":
            f, lines, lh = fit_text(text, "Black", max_w, 900, 128)
            layers.append(text_layer(W, H, lines, f, lh, txt, y_center=int(H * 0.46)))
        elif kind == "point":
            f, lines, lh = fit_text(text, "Bold", max_w, 800, 104)
            layers.append(text_layer(W, H, lines, f, lh, txt, y_center=int(H * 0.52)))
        else:
            f, lines, lh = fit_text(text, "Black", max_w, 700, 112)
            layers.append(text_layer(W, H, lines, f, lh, accent, y_center=int(H * 0.48)))
    layers_np = [np.asarray(l, np.float32) / 255.0 for l in layers]

    badge_font, handle_font = font("Black", 64), font("Medium", 44)
    bg = gradient(W, H, hex_rgb(st["bg_top"]), hex_rgb(st["bg_bottom"]))
    b_alpha, b_color = blob(900, accent)

    starts, acc = [], 0.0
    for s in scenes:
        starts.append(acc)
        acc += s[2]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        *music_input(item["id"], total, st["music_volume"]),
        "-filter_complex",
        f"[1:a]volume={st['music_volume'] * 4:.2f},afade=t=in:d=0.6,afade=t=out:st={total - 1:.2f}:d=1,atrim=0:{total:.2f}[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    for fi in range(n_frames):
        t = fi / FPS
        si = max(i for i, s in enumerate(starts) if s <= t + 1e-6)
        kind, _, dur = scenes[si]
        lt = t - starts[si]

        frame = bg.copy()
        # blob que flota
        bx = int(W * 0.5 + W * 0.35 * np.sin(t * 0.6)) - 450
        by = int(H * 0.35 + H * 0.15 * np.cos(t * 0.45)) - 450
        x0, y0, x1, y1 = max(bx, 0), max(by, 0), min(bx + 900, W), min(by + 900, H)
        if x1 > x0 and y1 > y0:
            a = b_alpha[y0 - by : y1 - by, x0 - bx : x1 - bx]
            frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - a) + b_color * a

        img = Image.fromarray(frame.astype(np.uint8))
        d = ImageDraw.Draw(img)

        # barra de progreso superior
        d.rounded_rectangle((60, 90, W - 60, 102), 6, fill=tuple(int(c * 0.35) for c in muted))
        d.rounded_rectangle((60, 90, 60 + int((W - 120) * t / total), 102), 6, fill=accent)

        # contador "1/4" en puntos
        if kind == "point":
            k = si
            p = ease_out(lt / 0.35)
            label = f"{k}/{n_points}"
            bw = badge_font.getlength(label) + 80
            cx, cy = W // 2, int(H * 0.30 - 40 * (1 - p))
            d.rounded_rectangle((cx - bw / 2, cy - 60, cx + bw / 2, cy + 60), 60, fill=accent)
            d.text((cx, cy), label, font=badge_font, fill=hex_rgb(st["bg_top"]), anchor="mm")

        # subrayado animado del hook
        if kind == "hook":
            p = ease_out((lt - 0.4) / 0.6)
            lw = int(360 * p)
            d.rounded_rectangle((W // 2 - lw // 2, int(H * 0.64), W // 2 + lw // 2, int(H * 0.64) + 16), 8, fill=accent)

        d.text((W // 2, H - 170), st["handle"], font=handle_font, fill=muted, anchor="mm")
        frame = np.asarray(img, np.float32)

        # texto: entra deslizando + fade, sale con fade
        p_in = ease_out(lt / 0.45)
        p_out = 1 - ease_out((lt - (dur - 0.25)) / 0.25) if kind != "cta" else 1.0
        alpha_mul = p_in * p_out
        if kind == "cta":
            alpha_mul *= 1.0
        dy = int(70 * (1 - p_in))
        L = layers_np[si]
        if dy:
            L = np.roll(L, dy, axis=0)
            L[:dy] = 0
        a = L[..., 3:4] * alpha_mul
        frame = frame * (1 - a) + L[..., :3] * 255 * a

        proc.stdin.write(frame.astype(np.uint8).tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg falló al renderizar")
    return out_path
