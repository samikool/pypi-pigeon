# Airgap Workflow

This guide covers the full operational workflow for users running pypi-pigeon in a true airgapped environment — where the mirror server has no internet access and updates are physically transported on removable media.

## The security model

In a proper airgap setup, the transfer media (USB drive, external HDD, etc.) is **wiped after every transfer**. Nothing accumulates on the drive between runs — it is write, carry, copy, wipe. This is the whole point of an airgap.

Because of this, the workflow is split into two sides:

- **Internet machine** — runs `pigeon sync`, writes new files to the drive
- **Airgapped server** — reads from the drive, rsyncs everything into place, runs `pigeon-merge.py`, drive is wiped

The supplement wheels are **not** wiped on the server side. They accumulate in `/opt/pigeon/supplement/dist/` across transfers. `pigeon-merge.py` is idempotent — re-merging a wheel that's already in the index is a no-op.

---

## Recommended server layout

Copy your entire pigeon workspace to `/opt/pigeon/` on the server and keep it there permanently. This is the folder where you ran `pigeon setup` on the internet side:

```
/opt/pigeon/
  pigeon.toml           ← your config, already has the right paths
  pigeon-merge.py       ← the standalone merge script
  requirements.txt      ← your supplement package list
  supplement/
    dist/               ← wheels accumulate here across transfers
```

With this layout, `pigeon-merge.py` finds `pigeon.toml` automatically and you never need to pass explicit flags. The server needs no Python packages installed — just Python 3.6+ which is already present on any modern Linux system.

---

## One-time server setup

On your first transfer, copy the full workspace onto the drive and drop it on the server:

**On the internet machine:**

```bash
pigeon setup      # configure pigeon.toml and generate bandersnatch.conf (one-time)
pigeon add requests numpy <any other packages>   # optional supplement packages
pigeon sync       # run bandersnatch + fetch supplement wheels
```

Plug in the transfer drive:

```bash
# Copy the full mirror (this is large — plan for it)
rsync -av /your/mirror/web/    /mnt/transfer/web/

# Copy the entire pigeon workspace
rsync -av /your/pigeon-workspace/  /mnt/transfer/pigeon/
```

Unplug. Walk it to the server.

**On the airgapped server:**

```bash
# Copy mirror to the share
rsync -av /mnt/transfer/web/     /share/pypimirror/web/

# Copy the pigeon workspace to its permanent home
rsync -av /mnt/transfer/pigeon/  /opt/pigeon/

# Fold supplement wheels into the mirror index
python3 /opt/pigeon/pigeon-merge.py
```

Wipe the drive. nginx serves immediately — no restart needed.

---

## Regular update cycle

Every subsequent transfer follows the same pattern — copy the whole workspace, copy the mirror, merge.

**On the internet machine:**

```bash
# Add any new packages you need (optional)
pigeon add <new-package>

# Pull latest packages from PyPI
pigeon sync
```

Plug in the (freshly wiped) transfer drive:

```bash
rsync -av /your/mirror/web/        /mnt/transfer/web/
rsync -av /your/pigeon-workspace/  /mnt/transfer/pigeon/
```

Unplug. Walk it over.

**On the airgapped server:**

```bash
rsync -av /mnt/transfer/web/     /share/pypimirror/web/
rsync -av /mnt/transfer/pigeon/  /opt/pigeon/

python3 /opt/pigeon/pigeon-merge.py
```

Wipe the drive.

Always copying the full workspace means you never have to think about what changed — `pigeon.toml`, `requirements.txt`, `pigeon-merge.py`, and any new supplement wheels all stay in sync automatically.

---

## Why you always run pigeon-merge.py after every transfer

bandersnatch regenerates `web/simple/<pkg>/index.html` for every package it manages on each sync. This overwrites any supplement links that were previously injected for those packages. `pigeon-merge.py` re-injects them. It is fast and safe to re-run — any wheel already present in the index is skipped.

---

## Checking what changed

If you set `diff_file` in `pigeon.toml`, bandersnatch writes a list of every file it added or removed during sync. You can review this before copying to the drive:

```toml
[mirror]
diff_file = "/your/mirror/last-sync-diff.txt"
```

```bash
cat /your/mirror/last-sync-diff.txt
```
