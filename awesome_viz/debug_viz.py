#!/usr/bin/env python3
"""Generate an HTML report or MP4 video from a serve_policy_mem --debug_dir output.

Each step shows: task, CoT text, current camera frames (with overlays),
and the full frame-buffer history as a filmstrip per camera (HTML only).

Usage:
    # Self-contained HTML (base64-embedded images) — can be slow for many steps
    python scripts/utils/debug_viz.py <debug_dir> [--out report.html] [--max_steps N]

    # MP4 video — cameras side by side, task/CoT text overlay, much faster to open
    python scripts/utils/debug_viz.py <debug_dir> --video [--out review.mp4] [--fps 5]

    # debug_dir can be the ip_port subdir or the parent (auto-discovers subdirs)
    python scripts/utils/debug_viz.py tmps/debug_serve/127.0.0.1_12345
    python scripts/utils/debug_viz.py tmps/debug_serve               # all clients
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path


# ──────── helpers ────────

def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _img_tag(path: Path, title: str = "", style: str = "") -> str:
    ext = path.suffix.lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return (
        f'<img src="data:image/{mime};base64,{_b64(path)}"'
        f' title="{title}" style="{style}" loading="lazy">'
    )


def _read_meta(step_dir: Path) -> tuple[str, str]:
    """Return (task, cot) from meta.txt."""
    meta = step_dir / "meta.txt"
    if not meta.exists():
        return "", ""
    task, cot = "", []
    for line in meta.read_text().splitlines():
        if line.startswith("task: "):
            task = line[6:]
        elif line.startswith("cot: "):
            cot.append(line[5:])
        else:
            cot.append(line)
    return task, "\n".join(cot)


def _sorted_cam_keys(paths: list[Path]) -> list[str]:
    """Return camera keys in a stable order: head first, then wrists."""
    keys = [p.stem for p in paths]
    order = {"head": 0, "left": 1, "right": 2}
    return sorted(keys, key=lambda k: next((v for s, v in order.items() if s in k), 9))


# ──────── HTML builder ────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #111; color: #e0e0e0; padding: 16px; }
h1 { font-size: 1.1rem; margin-bottom: 16px; color: #aaa; }
.step { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
        margin-bottom: 20px; padding: 14px; }
.step-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 10px; }
.step-num { font-size: 0.8rem; font-weight: 600; color: #666; min-width: 70px; }
.task-text { font-size: 0.85rem; color: #c0c0c0; }
.cot-box { background: #0d1f0d; border-left: 3px solid #3a7d3a; border-radius: 4px;
           padding: 8px 12px; margin-bottom: 10px; font-size: 0.8rem;
           color: #90c990; white-space: pre-wrap; word-break: break-word; }
.cameras { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.cam-block { display: flex; flex-direction: column; gap: 4px; }
.cam-label { font-size: 0.7rem; color: #666; text-align: center; }
.cam-block img { border-radius: 4px; border: 1px solid #333; max-height: 200px; }
.history-section { margin-top: 6px; }
.history-label { font-size: 0.7rem; color: #555; margin-bottom: 4px; }
.filmstrip { display: flex; gap: 4px; overflow-x: auto; padding-bottom: 4px; }
.filmstrip-cam { margin-bottom: 8px; }
.filmstrip-cam-label { font-size: 0.68rem; color: #555; margin-bottom: 2px; }
.filmstrip img { height: 90px; border-radius: 3px; border: 1px solid #2a2a2a;
                  flex-shrink: 0; }
.filmstrip img:last-child { border-color: #4a7a4a; }
"""

_JS = """
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown' || e.key === 'j') {
    const steps = document.querySelectorAll('.step');
    const vh = window.scrollY + window.innerHeight / 2;
    for (const s of steps) {
      if (s.offsetTop > vh) { s.scrollIntoView({behavior:'smooth',block:'start'}); return; }
    }
  } else if (e.key === 'ArrowUp' || e.key === 'k') {
    const steps = [...document.querySelectorAll('.step')];
    const vh = window.scrollY + window.innerHeight / 2;
    for (const s of steps.reverse()) {
      if (s.offsetTop < vh - 10) { s.scrollIntoView({behavior:'smooth',block:'start'}); return; }
    }
  }
});
"""


def _render_step(step_dir: Path, step_idx: int) -> str:
    task, cot = _read_meta(step_dir)

    # Current frames (top-level jpgs)
    current_imgs = sorted(step_dir.glob("*.jpg"))
    cam_keys = _sorted_cam_keys(current_imgs)
    img_map = {p.stem: p for p in current_imgs}

    # History frames: history/{cam}_t{N}.jpg
    hist_dir = step_dir / "history"
    hist: dict[str, list[Path]] = {}
    if hist_dir.exists():
        for p in sorted(hist_dir.glob("*.jpg")):
            m = re.match(r"^(.+)_t(\d+)$", p.stem)
            if m:
                hist.setdefault(m.group(1), []).append(p)
        for v in hist.values():
            v.sort(key=lambda p: int(re.search(r"_t(\d+)$", p.stem).group(1)))

    html = [f'<div class="step" id="step-{step_idx:06d}">']

    # Header
    html.append('<div class="step-header">')
    html.append(f'<span class="step-num">step {step_idx:06d}</span>')
    if task:
        html.append(f'<span class="task-text">{task}</span>')
    html.append('</div>')

    # CoT
    if cot:
        html.append(f'<div class="cot-box">{cot}</div>')

    # Current frames
    if cam_keys:
        html.append('<div class="cameras">')
        for key in cam_keys:
            if key not in img_map:
                continue
            html.append('<div class="cam-block">')
            html.append(f'<div class="cam-label">{key}</div>')
            html.append(_img_tag(img_map[key], title=key))
            html.append('</div>')
        html.append('</div>')

    # History filmstrip per camera
    if hist:
        html.append('<div class="history-section">')
        html.append('<div class="history-label">frame buffer history (t0=oldest → tN=current)</div>')
        for key in cam_keys:
            frames = hist.get(key, [])
            if not frames:
                continue
            html.append('<div class="filmstrip-cam">')
            html.append(f'<div class="filmstrip-cam-label">{key}</div>')
            html.append('<div class="filmstrip">')
            for p in frames:
                t = int(re.search(r"_t(\d+)$", p.stem).group(1))
                html.append(_img_tag(p, title=f"t={t}", style=""))
            html.append('</div></div>')
        html.append('</div>')

    html.append('</div>')
    return "\n".join(html)


def _find_step_dirs(debug_dir: Path) -> list[Path]:
    """Locate step_* dirs under debug_dir or one level deeper (client subdirs)."""
    step_dirs = sorted(debug_dir.glob("step_*/"), key=lambda p: p.name)
    if not step_dirs:
        step_dirs = sorted(
            p for client in sorted(debug_dir.iterdir()) if client.is_dir()
            for p in sorted(client.glob("step_*/"), key=lambda p: p.name)
        )
    return step_dirs


def generate_report(debug_dir: Path, out_path: Path, max_steps: int | None = None) -> None:
    step_dirs = _find_step_dirs(debug_dir)
    if not step_dirs:
        print(f"No step_* directories found under {debug_dir}", file=sys.stderr)
        sys.exit(1)

    if max_steps:
        step_dirs = step_dirs[:max_steps]

    print(f"Rendering {len(step_dirs)} steps → {out_path}")

    body_parts = []
    for i, d in enumerate(step_dirs):
        step_idx = int(re.search(r"step_(\d+)", d.name).group(1))
        body_parts.append(_render_step(d, step_idx))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(step_dirs)} steps rendered...")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Debug: {debug_dir.name}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>serve_policy_mem debug — {debug_dir.resolve()}</h1>
{"".join(body_parts)}
<script>{_JS}</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    print(f"Done. Open: {out_path.resolve()}")


# ──────── video ────────

def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Wrap text to lines of at most max_chars, splitting on spaces."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def _compose_video_frame(
    step_dir: Path,
    step_idx: int,
    panel_h: int,
    text_bar_h: int,
) -> "np.ndarray | None":
    """Compose one video frame for a single inference step.

    Layout (per camera, stacked vertically):
        [t0] [t1] ... [tN-1] [tN=current★]   ← history row for cam0
        [t0] [t1] ... [tN-1] [tN=current★]   ← history row for cam1
        ...
        ─────────── task / CoT text bar ───────────

    History frames come from history/{cam}_t{i:02d}.jpg.
    The current rendered frame (with overlays) is the rightmost column.
    A green border marks the current frame in each row.
    """
    import cv2
    import numpy as np

    task, cot = _read_meta(step_dir)
    current_imgs = sorted(step_dir.glob("*.jpg"))
    cam_keys = _sorted_cam_keys(current_imgs)
    img_map = {p.stem: p for p in current_imgs}

    # Load history frames per camera: {cam_key: [bgr_t0, bgr_t1, ..., bgr_tN]}
    hist_dir = step_dir / "history"
    hist: dict[str, list] = {}
    if hist_dir.exists():
        for p in sorted(hist_dir.glob("*.jpg")):
            m = re.match(r"^(.+)_t(\d+)$", p.stem)
            if not m:
                continue
            cam, t = m.group(1), int(m.group(2))
            bgr = cv2.imread(str(p))
            if bgr is not None:
                hist.setdefault(cam, []).append((t, bgr))
        for cam in hist:
            hist[cam] = [bgr for _, bgr in sorted(hist[cam], key=lambda x: x[0])]

    def _resize_h(bgr, h):
        oh, ow = bgr.shape[:2]
        return cv2.resize(bgr, (max(1, int(round(ow * h / oh))), h))

    cam_rows = []
    panel_w = None  # infer from first current image

    for key in cam_keys:
        if key not in img_map:
            continue
        cur_bgr = cv2.imread(str(img_map[key]))
        if cur_bgr is None:
            continue
        cur_resized = _resize_h(cur_bgr, panel_h)
        if panel_w is None:
            panel_w = cur_resized.shape[1]

        frames_in_row = []
        if key in hist:
            for hbgr in hist[key]:
                frames_in_row.append(_resize_h(hbgr, panel_h))
        # Current frame (with overlays): green border to distinguish
        cur_marked = cur_resized.copy()
        cv2.rectangle(cur_marked, (0, 0),
                      (cur_marked.shape[1] - 1, cur_marked.shape[0] - 1),
                      (0, 200, 60), 3)
        frames_in_row.append(cur_marked)

        cam_rows.append(np.concatenate(frames_in_row, axis=1))

    if not cam_rows:
        return None

    # Pad all rows to the same width
    max_w = max(r.shape[1] for r in cam_rows)
    padded = []
    for r in cam_rows:
        if r.shape[1] < max_w:
            pad = np.zeros((r.shape[0], max_w - r.shape[1], 3), dtype=np.uint8)
            r = np.concatenate([r, pad], axis=1)
        padded.append(r)

    grid = np.concatenate(padded, axis=0)
    total_w = grid.shape[1]

    # Text bar
    bar = np.zeros((text_bar_h, total_w, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale, thickness, line_h = 2.5, 3, 60
    chars_per_line = max(10, total_w // 30)

    y = 14
    cv2.putText(bar, f"step {step_idx:06d}", (6, y), font, 1.5,
                (100, 100, 100), 2, cv2.LINE_AA)
    y += line_h
    if task:
        for line in _wrap_text(f"task: {task}", chars_per_line):
            if y + line_h > text_bar_h:
                break
            cv2.putText(bar, line, (6, y), font, font_scale,
                        (180, 180, 180), thickness, cv2.LINE_AA)
            y += line_h
    if cot:
        for line in _wrap_text(f"cot: {cot}", chars_per_line):
            if y + line_h > text_bar_h:
                break
            cv2.putText(bar, line, (6, y), font, font_scale,
                        (100, 200, 100), thickness, cv2.LINE_AA)
            y += line_h

    return np.concatenate([grid, bar], axis=0)


def generate_video(
    debug_dir: Path,
    out_path: Path,
    fps: float = 5.0,
    panel_h: int = 360,
    text_bar_h: int = 400,
    max_steps: int | None = None,
) -> None:
    import cv2

    step_dirs = _find_step_dirs(debug_dir)
    if not step_dirs:
        print(f"No step_* directories found under {debug_dir}", file=sys.stderr)
        sys.exit(1)
    if max_steps:
        step_dirs = step_dirs[:max_steps]

    print(f"Composing {len(step_dirs)} frames → {out_path} ({fps} fps)")

    writer = None
    for i, d in enumerate(step_dirs):
        step_idx = int(re.search(r"step_(\d+)", d.name).group(1))
        frame = _compose_video_frame(d, step_idx, panel_h, text_bar_h)
        if frame is None:
            continue
        if writer is None:
            h, w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        writer.write(frame)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(step_dirs)} frames written...")

    if writer is not None:
        writer.release()
        print(f"Done. Video: {out_path.resolve()}")
    else:
        print("No frames written — check that step dirs contain .jpg files.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML report or MP4 video from --debug_dir output"
    )
    parser.add_argument("debug_dir", type=Path, help="Path to debug_dir (or client subdir)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output path (default: debug_dir/report.html or review.mp4)")
    parser.add_argument("--max_steps", type=int, default=None, help="Limit number of steps")
    parser.add_argument("--video", action="store_true",
                        help="Generate MP4 video instead of HTML")
    parser.add_argument("--fps", type=float, default=5.0,
                        help="Frames per second for video (default: 5)")
    parser.add_argument("--text_bar_h", type=int, default=400,
                        help="Height of the CoT/task text bar in pixels (default: 400)")
    args = parser.parse_args()

    if args.video:
        out = args.out or (args.debug_dir / "review.mp4")
        generate_video(args.debug_dir, out, fps=args.fps,
                       text_bar_h=args.text_bar_h, max_steps=args.max_steps)
    else:
        out = args.out or (args.debug_dir / "report.html")
        generate_report(args.debug_dir, out, args.max_steps)


if __name__ == "__main__":
    main()
