"""Clone my code for Ed challenges that use git submission (e.g. COMP2017, INFO1112, COMP2123 assignments).

Needs an SSH key registered in Ed (Settings -> SSH Keys). Each challenge's repository lives at
git@git.edstem.org:challenge/<challenge id>/<any name>; cloning gives the full history of what I pushed.
Some challenges are flagged as git but have git turned off ("git is not enabled for this challenge") —
those are reported and their code has to be taken from the Ed website instead.

usage:
  python ed_git_clone.py --out Canvas-Backup        (reads Canvas-Backup/_ed-git-challenges.json)
"""
import argparse, json, os, subprocess, sys

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--out", required=True)
ap.add_argument("--all", action="store_true", help="also try challenges not flagged as git (normally pointless)")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")
items = json.load(open(os.path.join(args.out, "_ed-git-challenges.json"), encoding="utf-8"))
env = dict(os.environ, GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=30 -o StrictHostKeyChecking=accept-new")
ok = fail = 0
for it in items:
    if not (it["git"] or args.all):
        continue
    dest = it["dir"]
    if os.path.isdir(os.path.join(dest, ".git")):
        print(f"{it['challenge_id']}: already cloned")
        ok += 1
        continue
    r = subprocess.run(["git", "-c", "core.longpaths=true", "clone", "-q",
                        f"git@git.edstem.org:challenge/{it['challenge_id']}/code", dest],
                       capture_output=True, text=True, env=env, timeout=600)
    if r.returncode == 0:
        subprocess.run(["git", "-C", dest, "config", "core.longpaths", "true"])
        n = subprocess.run(["git", "-C", dest, "rev-list", "--all", "--count"], capture_output=True, text=True).stdout.strip()
        print(f"{it['challenge_id']}: OK  {it['title']} ({n} commits)")
        ok += 1
    else:
        msg = (r.stderr.strip().splitlines() or ["?"])[-1]
        if "Permission denied (publickey)" in msg:
            sys.exit("Ed rejected the SSH key: add ~/.ssh/id_ed25519.pub in Ed -> Settings -> SSH Keys, then re-run.")
        print(f"{it['challenge_id']}: not available  {it['title']} — {msg[:120]}")
        it["git"] = False   # treat as a browser task
        fail += 1
json.dump(items, open(os.path.join(args.out, "_ed-git-challenges.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\ncloned {ok}, not available {fail} (those are listed for the browser by ed_browser_tasks.py)")
