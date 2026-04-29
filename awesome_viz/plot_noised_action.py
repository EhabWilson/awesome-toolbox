import numpy as np
import matplotlib.pyplot as plt
import os

np.random.seed(0)

horizon = 20
action_dim = 4
t = np.linspace(0, 1, horizon)
t_smooth = np.linspace(0, 1, 400)

# Structured action chunk
action_chunk = np.zeros((horizon, action_dim))
freqs  = [1.0, 1.3, 0.7, 1.6]
phases = [0, np.pi/4, np.pi/2, np.pi]
for i in range(3):
    action_chunk[:, i] = np.sin(freqs[i] * 2 * np.pi * t + phases[i]) * 0.85
gripper = np.ones(horizon)
gripper[7:] = -1.0
action_chunk[:, 3] = gripper

# Pure noise clipped to [-1, 1]
noise = np.clip(np.random.randn(horizon, action_dim), -1, 1)

weights = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

def catmull_rom(t_in, y_in, t_out):
    n = len(t_in)
    result = np.zeros_like(t_out)
    for k, tv in enumerate(t_out):
        idx = np.clip(np.searchsorted(t_in, tv, side='right') - 1, 1, n - 3)
        i0, i1, i2, i3 = idx - 1, idx, idx + 1, idx + 2
        p0, p1, p2, p3 = y_in[i0], y_in[i1], y_in[i2], y_in[i3]
        t1, t2 = t_in[i1], t_in[i2]
        u = (tv - t1) / (t2 - t1 + 1e-12)
        u2, u3 = u*u, u*u*u
        result[k] = 0.5 * ((-u3+2*u2-u)*p0 + (3*u3-5*u2+2)*p1 +
                           (-3*u3+4*u2+u)*p2 + (u3-u2)*p3)
    return result

colors = [
    (115/255, 141/255, 187/255),
    (140/255, 178/255, 111/255),
    (206/255, 158/255,  53/255),
    (209/255, 183/255, 101/255),
]

out_dir = "/Users/yuhang/workspace/awesome-toolbox/action_frames"
os.makedirs(out_dir, exist_ok=True)

for w in weights:
    blended = (1.0 - w) * action_chunk + w * noise

    fig, axes = plt.subplots(action_dim, 1,
                             figsize=(3, 4),
                             gridspec_kw={"hspace": 0.08})
    fig.patch.set_alpha(0.0)

    for row in range(action_dim):
        ax = axes[row]
        ax.set_facecolor("none")
        ax.set_xlim(0, 1)
        ax.set_ylim(-1.35, 1.35)
        ax.axis("off")

        y = blended[:, row]
        color = colors[row]
        is_gripper = (row == action_dim - 1)

        if is_gripper:
            ax.plot(t, y, color=color, lw=4)
        else:
            ax.plot(t_smooth, catmull_rom(t, y, t_smooth), color=color, lw=4)

    fname = os.path.join(out_dir, f"w{int(round(w*10)):02d}.png")
    plt.savefig(fname, dpi=180, bbox_inches="tight", facecolor="none", transparent=True)
    plt.close(fig)
    print(f"Saved {fname}")
