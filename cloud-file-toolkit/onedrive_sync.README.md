# onedrive_sync.sh

A small, reusable script that keeps **one OneDrive folder mirrored with one local
folder** in both directions, driven by a per-sync macOS launchd agent. Used today
for a Zotero attachment store and an Obsidian research vault, but works for any
folder pair.

## What it does

```bash
onedrive_sync.sh <remote> <local>
```

Runs two `rclone copy --update` passes:

```
<remote>  -->  <local>    # pull
<local>   -->  <remote>   # push
```

- `--update` = **newer-wins**: a file is overwritten only if the source is newer
  than the destination, so in-progress edits on either side are not clobbered by an
  older copy.
- A `mkdir`-based lock at `/tmp/onedrive_sync.<md5 of local path>.lock` prevents a
  job from overlapping itself (e.g. file-change trigger + timer firing together).
  The lock is keyed to the local path, so different sync pairs never block each
  other.
- `rclone` is invoked by absolute path (`/opt/homebrew/bin/rclone`) because launchd
  has no Homebrew `PATH`.

## Active sync pairs

The concrete remote/local folder paths are configured **only in the launchd plists**
under `~/Library/LaunchAgents/` — they are intentionally **not** stored in this repo,
so private folder names are not exposed in git history.

| Purpose            | launchd label              | Log                                |
|--------------------|----------------------------|------------------------------------|
| Zotero attachments | `com.yuhang.zotero-sync`   | `~/Library/Logs/zotero_sync.log`   |
| Research vault     | `com.yuhang.research-sync` | `~/Library/Logs/research_sync.log` |

To see the actual paths for a pair, read its plist's `ProgramArguments`.

## How it runs (launchd)

Each pair has its own LaunchAgent in `~/Library/LaunchAgents/`. Both use the same
triggers:

| Trigger            | Setting                 | Effect                                          |
|--------------------|-------------------------|-------------------------------------------------|
| Local file change  | `WatchPaths` on `<local>` | Sync runs shortly after local files change      |
| Periodic           | `StartInterval` = 1800  | Sync every 30 min (catches remote-side changes) |
| Login / agent load | `RunAtLoad`             | Sync once at startup                            |
| Debounce           | `ThrottleInterval` = 60 | Coalesces bursts so runs don't stack            |

### Managing an agent

Replace `<label>` with `com.yuhang.zotero-sync` or `com.yuhang.research-sync`:

```bash
launchctl list | grep -E 'zotero-sync|research-sync'                 # status
launchctl kickstart -k gui/$(id -u)/<label>                          # run now
launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/<label>.plist  # stop/unload
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist  # load
```

> After moving/renaming the script, update each plist's `ProgramArguments` path and
> reload the agent (bootout + bootstrap).

### Adding a new sync pair

1. Copy a plist, change its `Label`, the two `ProgramArguments` after the script
   (`<remote>` and `<local>`), `WatchPaths`, and the log path.
2. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<new>.plist`.

## ⚠️ Cautions

- **Never sync a live database.** Bidirectional file-sync of e.g. `zotero.sqlite`
  while the app is open can corrupt it. The Zotero pair deliberately syncs only the
  attachment-files subfolder; library metadata goes through Zotero's own account
  sync. Keep databases out of any synced folder.
- **`copy` does not propagate deletions.** A file deleted on one side is restored
  from the other on the next run. Safer against accidental loss, but to truly remove
  something you must delete it on both sides.
- **Newer-wins, not conflict-aware.** If the *same* file is edited on two devices
  between syncs, the older-timestamped edit is lost silently (no conflict copy is
  kept). This matters most for the actively-edited Obsidian vault — let one device
  finish syncing before editing on another. Clock skew between machines can also
  misjudge "newer."
- **Hard-coded `rclone` path.** Uses `/opt/homebrew/bin/rclone`; adjust if rclone
  lives elsewhere.

## Requirements

- [`rclone`](https://rclone.org) configured with a remote named `onedrive`
  (`rclone listremotes` should show `onedrive:`).
- macOS (uses `launchd`).
