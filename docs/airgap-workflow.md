# Airgap Workflow

This guide covers the full operational workflow for users running pypi-pigeon in a true airgapped environment — where the mirror server has no internet access and updates are physically transported on removable media.

## The security model

In a proper airgap setup, the transfer media (USB drive, external HDD, etc.) is **wiped after every transfer**. Nothing accumulates on the drive between runs — it is write, carry, copy, wipe. This is the whole point of an airgap.

Because of this, the workflow is split into two sides:

- **Internet machine** — runs `pigeon sync`, writes new files to the drive
- **Airgapped server** — reads from the drive, copies to the mirror, runs `pigeon-merge.py`, drive is wiped

The supplement wheels are **not** wiped on the server side. They accumulate in a permanent directory. `pigeon-merge.py` is idempotent — re-merging a wheel that's already in the index is a no-op.

---

## One-time server setup

Do this once when you first set up the server.

```bash
# Pick a permanent home for the standalone merge script and supplement wheels
mkdir -p /opt/pigeon/supplement/dist

# Copy pigeon-merge.py from the transfer drive
cp /mnt/transfer/pigeon-merge.py /opt/pigeon/pigeon-merge.py
```

That's it. The server needs no Python packages installed — just Python 3.6+ which is already present on any modern Linux system.

---

## First transfer (initial mirror setup)

**On the internet machine:**

```bash
pigeon setup      # configure pigeon.toml and generate bandersnatch.conf (one-time)
pigeon add requests numpy <any other packages>   # optional supplement packages
pigeon sync       # run bandersnatch + fetch supplement wheels
```

Plug in the transfer drive and copy the mirror onto it:

```bash
# Copy the full mirror (this is large — plan for it)
rsync -av /your/mirror/web/    /mnt/transfer/web/
rsync -av supplement/dist/     /mnt/transfer/supplement/dist/

# Also copy the merge script if you haven't already
cp pigeon-merge.py /mnt/transfer/pigeon-merge.py
```

Unplug drive. Walk it to the server.

**On the airgapped server:**

```bash
# Copy mirror to the share
rsync -av /mnt/transfer/web/              /share/pypimirror/web/

# Copy supplement wheels to the permanent directory
rsync -av /mnt/transfer/supplement/dist/  /opt/pigeon/supplement/dist/

# Fold supplement wheels into the mirror index
python3 /opt/pigeon/pigeon-merge.py \
    --mirror /share/pypimirror \
    --dist   /opt/pigeon/supplement/dist
```

Wipe the drive. nginx serves immediately — no restart needed.

---

## Regular update cycle

**On the internet machine:**

```bash
# Add any new packages you need (optional)
pigeon add <new-package>

# Pull latest packages from PyPI
pigeon sync
```

Plug in the (freshly wiped) transfer drive:

```bash
# Sync only what changed — bandersnatch is incremental so this is fast
rsync -av /your/mirror/web/    /mnt/transfer/web/
rsync -av supplement/dist/     /mnt/transfer/supplement/dist/
```

Unplug. Walk it over.

**On the airgapped server:**

```bash
rsync -av /mnt/transfer/web/              /share/pypimirror/web/
rsync -av /mnt/transfer/supplement/dist/  /opt/pigeon/supplement/dist/

python3 /opt/pigeon/pigeon-merge.py \
    --mirror /share/pypimirror \
    --dist   /opt/pigeon/supplement/dist
```

Wipe the drive.

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

---

## pigeon-merge.py path auto-detection

If you keep `pigeon.toml` on the server alongside the merge script, you can omit the explicit flags:

```bash
python3 /opt/pigeon/pigeon-merge.py   # reads paths from pigeon.toml automatically
```

The script walks up the directory tree from wherever it's run, looking for `pigeon.toml` — the same way the `pigeon` CLI does.
