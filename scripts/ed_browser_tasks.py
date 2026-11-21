"""Write the English browser checklist for Ed items the API can't fetch, for a browser agent
(e.g. Claude in Chrome) or for doing it by hand:
  Part A — course Resources (Ed's file host needs the logged-in browser session)
  Part B — my code for non-git coding challenges (only shown in Ed's Submissions view; slow: ~2 h per 300)
Also writes _ed-resources-manifest.json, which sort_downloads.py uses to file the downloads.

usage:
  python ed_browser_tasks.py --env .env --out Canvas-Backup [--no-challenges] [--assignments-only]
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ed_backup as eb

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--env", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--no-challenges", action="store_true", help="only list resources (Part A)")
ap.add_argument("--assignments-only", action="store_true", help="Part B: only challenges in lessons whose title "
                                                                  "mentions Assignment/Project/Milestone")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")
eb.init(args.env, args.out)
me, courses = eb.ed_courses()
OUT = eb.OUT

manifest, partA = [], []
for c in courses:
    cdir = eb.course_dir(c)
    rs = [r for r in (eb.getj(f"/courses/{c['id']}/resources") or {}).get("resources", []) if not r.get("link")]
    if not cdir or not rs:
        continue
    mb = sum(r.get("size") or 0 for r in rs) / 1e6
    partA += [f"### {c.get('code')} ({c.get('year')} {c.get('session')}) — {len(rs)} files, {mb:.1f} MB",
              f"Resources page: https://edstem.org/au/courses/{c['id']}/resources", ""]
    for r in sorted(rs, key=lambda r: (r.get("category") or "", r["name"])):
        partA.append(f"- [ ] {r.get('category') or 'General'} / {r['name']}{r.get('extension') or ''}")
        manifest.append({"id": r["id"], "course_id": c["id"], "folder": os.path.join(cdir, "ed", "resources"),
                         "category": r.get("category") or "General", "name": r["name"], "extension": r.get("extension") or "",
                         "session": (r.get("session") or "").strip(), "size": r.get("size")})
    partA.append("")
json.dump(manifest, open(os.path.join(OUT, "_ed-resources-manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

partB, n_chal = [], 0
if not args.no_challenges:
    items = json.load(open(os.path.join(OUT, "_ed-git-challenges.json"), encoding="utf-8"))
    names = {c["id"]: c for c in courses}
    todo = [i for i in items if not os.path.isdir(os.path.join(i["dir"], ".git"))]
    if args.assignments_only:
        todo = [i for i in todo if any(k in (i.get("lesson") or "") + (i.get("title") or "") for k in ("Assignment", "Project", "Milestone"))]
    for cid in dict.fromkeys(i["course_id"] for i in todo):
        c, mine = names[cid], [i for i in todo if i["course_id"] == cid]
        partB += [f"### {c.get('code')} ({c.get('year')} {c.get('session')}) — {len(mine)} challenges", ""]
        for i in sorted(mine, key=lambda i: (i.get("lesson") or "", i["challenge_id"])):
            partB.append(f"- [ ] challenge id **{i['challenge_id']}** — {i.get('lesson')} / {i.get('title')} "
                         f"({i['submissions']} submissions): https://edstem.org/au/courses/{cid}/lessons/{i['lesson_id']}/slides/{i['slide_id']}")
            n_chal += 1
        partB.append("")

lines = ["# Ed (edstem.org) — items to fetch in the browser", "",
         "Log in to https://edstem.org/au with the University of Sydney account first. Save everything into the normal",
         "**Downloads** folder. This is a read-only backup: do not submit, run, mark, reset or change anything in Ed.",
         "Afterwards `sort_downloads.py` files every download into the backup.", "",
         f"**Part A: {len(manifest)} resource files. Part B: {n_chal} challenges.**", "", "---", "",
         "## Part A — Course resources", "",
         "Open each course's Resources page and download every file listed, keeping the file names Ed gives them",
         "(Ed may prefix the week, e.g. `Week 1 - Introduction to Bash.pdf` — that's fine). One course at a time.", ""] + partA
if partB:
    lines += ["---", "", "## Part B — My code for non-git coding challenges", "",
              "For each link: open it, open the **Submissions** view, pick the **most recent** submission and download its",
              "files (use Ed's download option if offered, otherwise copy each file into a text file). Name every saved file",
              "`ed-<challenge id>-<original file name>` (e.g. `ed-56753-book.py`). Never save the JSON that some download",
              "buttons return (it contains a one-time `ticket`, not code). Do not press Submit, Run, Mark or Reset.", ""] + partB
dest = os.path.join(OUT, "_ed-browser-tasks.md")
open(dest, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"Part A: {len(manifest)} resources; Part B: {n_chal} challenges -> {dest}")
