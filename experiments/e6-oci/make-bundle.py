#!/usr/bin/env python3
"""
experiments/e6-oci/make-bundle.py

Build a deterministic tar.gz of an AIX bundle directory for pushing as a
single OCI artifact layer (E6, plan docs/plans/2026-09-26-federation-experiments-plan.md).

Determinism rules (so the same bundle content always produces the same
digest, and only a real content change moves the digest):
  - Entries added in sorted path order.
  - Fixed mtime (epoch 0) on every tar entry AND on the gzip header
    (gzip stores its own mtime field independently of the tar entries).
  - uid=0, gid=0, uname="", gname="" on every entry (--owner=0 --group=0
    equivalent).
  - gzip compresslevel fixed (9) and mtime=0 so the gzip wrapper itself
    is reproducible, not just the tar stream inside it.

Usage:
    make-bundle.py <source-dir> <output.tar.gz> [--root-name NAME]

<root-name> is the directory name entries are rooted under inside the
archive (default: basename of source-dir), mirroring the
"rooted at <skill-name>/" convention from the agents-skills-oci-artifacts
reference spec so the layout is comparable.
"""
import argparse
import gzip
import io
import os
import sys
import tarfile


def deterministic_filter(root_name, source_dir):
    def _filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
        tarinfo.mtime = 0
        tarinfo.uid = 0
        tarinfo.gid = 0
        tarinfo.uname = ""
        tarinfo.gname = ""
        return tarinfo

    return _filter


def collect_sorted_paths(source_dir):
    """Return every file path under source_dir, sorted, for deterministic add order."""
    paths = []
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames.sort()
        for fn in sorted(filenames):
            paths.append(os.path.join(dirpath, fn))
    paths.sort()
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source_dir")
    ap.add_argument("output")
    ap.add_argument("--root-name", default=None)
    args = ap.parse_args()

    source_dir = os.path.abspath(args.source_dir)
    root_name = args.root_name or os.path.basename(source_dir.rstrip("/"))

    files = collect_sorted_paths(source_dir)
    if not files:
        print(f"error: no files found under {source_dir}", file=sys.stderr)
        sys.exit(1)

    # Build the tar stream in memory, then gzip it with a fixed mtime.
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for abspath in files:
            relpath = os.path.relpath(abspath, source_dir)
            arcname = f"{root_name}/{relpath}"
            tf.add(abspath, arcname=arcname, filter=deterministic_filter(root_name, source_dir))

    tar_bytes = tar_buf.getvalue()

    with open(args.output, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9) as gz:
            gz.write(tar_bytes)

    print(f"wrote {args.output} ({os.path.getsize(args.output)} bytes, {len(files)} files, root {root_name}/)")


if __name__ == "__main__":
    main()
