#!/usr/bin/env python3
"""Zip every plugin and write index.json (run on each release; CI can do it later).

Usage: python tools/make_index.py --base-url https://github.com/ORG/cytoflowplugins/releases/download/TAG/
  -> dist/<id>-<version>.zip   (upload these to the GitHub release TAG)
  -> index.json                (commit to the main branch)
Zips are reproducible (fixed timestamps), so unchanged plugins keep the same SHA-256.
"""
import argparse
import hashlib
import json
import tomllib
import zipfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--base-url", required=True)
ap.add_argument("--plugins", default="plugins")
ap.add_argument("--dist", default="dist")
ap.add_argument("--index", default="index.json")
a = ap.parse_args()

dist = Path(a.dist)
dist.mkdir(exist_ok=True)
entries = []
for folder in sorted(p for p in Path(a.plugins).iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
    d = tomllib.loads((folder / "plugin.toml").read_text(encoding="utf-8"))
    if d.get("user") is True:
        raise SystemExit(f"{folder.name}: 'user = true' in plugin.toml marks a plugin created in the "
                         "application; remove that line before publishing it")
    zpath = dist / f"{d['id']}-{d['version']}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                zi = zipfile.ZipInfo(f.relative_to(folder).as_posix(), (2020, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                z.writestr(zi, f.read_bytes())
    entries.append({
        "id": d["id"], "name": d["name"], "version": d["version"],
        "api_version": d["api_version"], "min_app": d.get("requires", {}).get("app", "0.0.0"),
        "url": a.base_url.rstrip("/") + "/" + zpath.name,
        "sha256": hashlib.sha256(zpath.read_bytes()).hexdigest(),
        "notes": d.get("notes", ""),
    })
    print("packed", zpath)
Path(a.index).write_text(json.dumps({"schema": 1, "plugins": entries}, indent=2), encoding="utf-8")
print("wrote", a.index)
