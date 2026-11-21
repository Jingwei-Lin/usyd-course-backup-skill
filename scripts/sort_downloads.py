"""File browser downloads (from _ed-browser-tasks.md) into the backup. Dry-run unless --move.

- Ed resources: matched to _ed-resources-manifest.json by file name — as listed, or with Ed's "<session> - "
  prefix (e.g. "Week 1 - Introduction to Bash.pdf") — and size; the browser's " (1)" suffixes are ignored.
  Identical files that appear in two offerings (e.g. INFO1110 2021 and 2022) are each filed once.
- Challenge code: files named ed-<challenge id>-<name> go to that challenge's submissions/.../code/ folder;
  zips are extracted there. Files that are really Ed download-ticket JSON are reported (and deleted on --move:
  they are one-time credentials, not code).
- Anything else is left in the Downloads folder and listed.

usage:
  python sort_downloads.py --downloads "%USERPROFILE%/Downloads" --out Canvas-Backup --since "2026-11-21 21:40" [--move]
"""
import argparse, collections, glob, json, os, re, shutil, sys, zipfile
from datetime import datetime

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--downloads", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--since", required=True, help="only consider files modified after this local time, 'YYYY-MM-DD HH:MM'")
ap.add_argument("--move", action="store_true")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")
BAD = r'[<>:"/\\|?*\x00-\x1f]'
since = datetime.strptime(args.since, "%Y-%m-%d %H:%M").timestamp()


def norm(n):
    n = re.sub(BAD, "_", n).strip()
    return re.sub(r" \(\d+\)(?=\.[^.]+$|$)", "", n).lower()


def is_ticket(path):
    try:
        head = open(path, "rb").read(200).lstrip()
        return head.startswith(b"{") and b'"ticket"' in head
    except OSError:
        return False


res = json.load(open(os.path.join(args.out, "_ed-resources-manifest.json"), encoding="utf-8"))
by_name = collections.defaultdict(list)
for r in res:
    by_name[norm(r["name"] + r["extension"])].append(r)
    if r.get("session"):
        by_name[norm(f"{r['session']} - {r['name']}{r['extension']}")].append(r)
chal_dir = {}
gc = os.path.join(args.out, "_ed-git-challenges.json")
if os.path.exists(gc):
    chal_dir = {str(i["challenge_id"]): i["dir"] for i in json.load(open(gc, encoding="utf-8"))}

files = sorted(p for p in glob.glob(os.path.join(args.downloads, "*"))
               if os.path.isfile(p) and os.path.getmtime(p) >= since and not p.endswith((".crdownload", ".part", ".tmp")))
plan, tickets, unmatched, claimed = [], [], [], set()
for p in files:
    base = os.path.basename(p)
    m = re.match(r"ed-(\d+)-(.+)$", base)
    if m and m.group(1) in chal_dir:
        if is_ticket(p):
            tickets.append(p)
        else:
            plan.append((p, os.path.join(chal_dir[m.group(1)], m.group(2)), "code"))
        continue
    cands = [r for r in by_name.get(norm(base), []) if id(r) not in claimed]
    exact = [r for r in cands if r.get("size") == os.path.getsize(p)]
    pick = exact or cands
    if not pick:
        unmatched.append(base)
        continue
    r = pick[0]
    claimed.add(id(r))
    dest = os.path.join(r["folder"], re.sub(BAD, "_", r["category"])[:50].strip(), re.sub(BAD, "_", r["name"] + r["extension"]))
    plan.append((p, dest, "resource" if exact else "resource (size differs)"))

kinds = collections.Counter(k.split(" ")[0] for *_, k in plan)
print(f"{len(files)} downloads since {args.since}: resources {kinds['resource']}, code {kinds['code']}, "
      f"ticket files {len(tickets)}, unmatched {len(unmatched)}")
print(f"resources in the manifest still missing: {len(res) - sum(1 for r in res if id(r) in claimed)}")
for b in unmatched[:30]:
    print("   unmatched:", b)
for t in tickets:
    print("   ticket JSON (not code):", os.path.basename(t))
if not args.move:
    print("\ndry run — re-run with --move to file them")
    sys.exit()
for src, dst, kind in plan:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if kind == "code" and zipfile.is_zipfile(src):
        zipfile.ZipFile(src).extractall(os.path.dirname(dst))
        os.remove(src)
        continue
    if os.path.exists(dst):
        stem, ext = os.path.splitext(dst)
        dst = f"{stem} (download){ext}"
    shutil.move(src, dst)
for t in tickets:
    os.remove(t)
print(f"filed {len(plan)} files, deleted {len(tickets)} ticket files")
