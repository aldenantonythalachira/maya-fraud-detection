"""Safe code checkpoints: python scripts/versions.py list|save NAME|restore TAG.

Restore creates a new branch. It never resets, cleans, or force-pushes.
Generated model/data files are deliberately outside code version recovery.
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def clean():
    if git("status", "--porcelain"):
        raise SystemExit("Local changes exist. Commit them on your current branch before continuing; no files changed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "save", "restore"])
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    if args.action == "list":
        print(git("tag", "--list", "maya/*", "--sort=-creatordate", "--format=%(refname:short) %(objectname:short) %(contents:subject)"))
        return
    if not args.name or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9/._-]{0,100}", args.name):
        parser.error("Provide a checkpoint name containing only letters, numbers, slash, dot, underscore or hyphen")
    clean()
    tag = args.name if args.name.startswith("maya/") else "maya/" + args.name
    if args.action == "save":
        git("tag", "-a", tag, "-m", "MAYA checkpoint: " + tag)
        print("Created " + tag + ". Publish with: git push origin " + tag)
    else:
        commit = git("rev-parse", "--verify", tag + "^{commit}")
        branch = "restore/" + tag.replace("maya/", "", 1) + "-" + commit[:7]
        git("switch", "-c", branch, commit)
        print("Restored code on " + branch + "; original branches and generated data are preserved.")


if __name__ == "__main__":
    main()
