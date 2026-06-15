import datetime
import os
import re

import matplotlib.pyplot as plt
import numpy as np


def next_versioned_path(out_dir, suffix, ext):
    """Return {out_dir}/{MMDD}v{i}{suffix}.{ext} with the next free i."""
    date_tag = datetime.date.today().strftime("%m%d")
    pattern = re.compile(rf"^{date_tag}v(\d+){re.escape(suffix)}\.{re.escape(ext)}$")
    used = set()
    if os.path.isdir(out_dir):
        for name in os.listdir(out_dir):
            m = pattern.match(name)
            if m:
                used.add(int(m.group(1)))
    i = 0
    while i in used:
        i += 1
    return os.path.join(out_dir, f"{date_tag}v{i}{suffix}.{ext}")


def gaussian_smooth(xs, ys, x_eval, bandwidth):
    """Nadaraya-Watson kernel smoother with a Gaussian kernel."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    x_eval = np.asarray(x_eval, dtype=float)
    diff = (x_eval[:, None] - xs[None, :]) / bandwidth
    w = np.exp(-0.5 * diff ** 2)
    return (w * ys[None, :]).sum(axis=1) / w.sum(axis=1)

steps = [2000, 4000, 8000, 12000, 16000, 18000, 20000, 24000,
         28000, 32000, 36000, 40000, 44000, 48000, 52000, 56000, 60000]

# Use None for missing entries.
models = {
    "CATok": [0, 0.031, 0.188, 0.26, 0.25, None, 0.375, 0.396,
              0.49, 0.427, 0.458, 0.542, 0.427, 0.406, 0.347, 0.46, 0.49],
    "FAST":  [0, 0.031, 0.26, 0.26, 0.292, None, None, None, 0.396,
              0.458, 0.396, None, 0.427, 0.474, 0.464, 0.429, 0.469],
}

colors = {
    "CATok": (115/255, 141/255, 187/255),
    "FAST":  (206/255, 158/255,  53/255),
}

fig, ax = plt.subplots(figsize=(9, 5))

# Kernel bandwidth in training-step units. Larger => smoother.
BANDWIDTH = 6000

for name, values in models.items():
    xs, ys = zip(*[(s, v) for s, v in zip(steps, values) if v is not None])
    xs_arr = np.asarray(xs, dtype=float)
    ys_arr = np.asarray(ys, dtype=float)
    color = colors.get(name)

    # Raw points as faded markers.
    ax.plot(xs_arr, ys_arr, marker="o", linestyle="none", markersize=5,
            color=color, alpha=0.45)

    # Smoothed fit via Gaussian kernel regression.
    x_smooth = np.linspace(xs_arr.min(), xs_arr.max(), 400)
    y_smooth = gaussian_smooth(xs_arr, ys_arr, x_smooth, BANDWIDTH)
    ax.plot(x_smooth, y_smooth, linewidth=2.2, color=color, label=name)

ax.set_xlabel("Training Steps")
ax.set_ylabel("Success Rate")
ax.set_title("Success Rate vs Training Steps")
ax.set_xticks(steps)
ax.set_xticklabels([f"{s//1000}k" for s in steps], rotation=45)
ax.set_xlim(2000, 40000)
ax.set_ylim(0, 0.5)
ax.grid(True, linestyle="--", alpha=0.4)
ax.legend()

plt.tight_layout()
out_dir = "/Users/yuhang/workspace/awesome-toolbox/awesome_viz"
pdf_path = next_versioned_path(out_dir, "_training_efficiency", "pdf")
# Mirror the PDF version tag so png/pdf stay in sync.
png_path = pdf_path[:-4] + ".png"
plt.savefig(png_path, dpi=150)
plt.savefig(pdf_path)
print(f"Saved figure to {png_path}")
print(f"Saved figure to {pdf_path}")
