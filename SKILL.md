---
name: usyd-course-backup
description: Back up a University of Sydney student's own coursework from Canvas (canvas.sydney.edu.au), Ed (edstem.org) and Gradescope before their student account closes — submitted assignments, grades, teacher feedback and rubrics, assignment specs, course materials and lecture slides, hidden Canvas pages, Ed lessons/quizzes/submission history, Ed git assignment code (e.g. COMP2017 PEX), and Gradescope graded copies — into one tidy term/course folder tree. Use this whenever a USYD student wants to download, save, export, archive or keep their Canvas/Ed/Gradescope stuff, mentions graduating or losing access to their uni account, asks to "back up my courses", "download all my assignments/lecture notes", "save my feedback/grades", or has a Canvas or Ed API token and wants to use it — even if they only name one of the three platforms.
---

# USYD course backup (Canvas + Ed + Gradescope)

Student accounts — and with them Canvas, Ed, Gradescope and the university OneDrive — stop working after
graduation. This skill exports everything the student can see into a folder tree they keep:

```
<backup>/                                  e.g. F:\USYD-Projects\Canvas-Backup
├─ README.md, grades.csv                   index of every course, every assignment's score
├─ 2024-S1/COMP3308/
│  ├─ materials/      Canvas modules (files, pages as offline HTML), Home, Syllabus, _linked-pages/, links.md
│  ├─ submissions/    my files per assignment (attempt-N/), feedback-files/, assignment-description.html + spec-files/
│  ├─ feedback.md     score, rubric and comments per assignment
│  ├─ ed/             lessons/, resources/, submissions/<lesson>/<challenge>/ (+ code/ git history)
│  └─ gradescope/     graded PDFs, original submissions, Final Exam/
├─ _personal-files/   the student's Canvas "My Files"
└─ _download-log.txt, _ed-browser-tasks.md, …   logs and browser checklists
```

The scripts in `scripts/` did this end-to-end for a real student (~70 Canvas courses, 42 Ed courses, ~17 GB).
Use them rather than rewriting; read `references/troubleshooting.md` when something looks off.

## Ground rules (and why)

- **Read-only.** Only GET requests; never submit, reset or change anything. A backup that alters coursework
  would be a disaster, and nothing here needs writes.
- **Tokens stay secret.** Keep them in a `.env` file outside any git repo; never print, echo or paste them.
  When you need to check `.env`, show key names and value lengths only. Send each token only to its own
  platform (Canvas token → canvas.sydney.edu.au, Ed token → edstem.org). If a step would need a token sent
  anywhere else, stop and ask the student — don't look for a workaround.
- **Play fair with the servers.** Use the documented APIs with an honest User-Agent (`requests` for Ed, as in
  Ed's own sample), keep Ed strictly sequential, back off on 429. Never disguise the client as a browser.
- **Dry-run first, then download.** Show the student how many files/GB will land where before writing anything.
- **It's their data, not a mirror of the course.** Course materials remain the University's/staff's copyright:
  personal reference only — say so in the final summary, and don't suggest publishing them.
- **Don't save into the university OneDrive** ("OneDrive - The University of Sydney (Students)"): it closes too.

Talk to the student in their language; they may not be technical. Explain each manual step (creating a token,
adding an SSH key) click by click.

## Step 0 — Setup

Requirements: Python 3.9+ with `requests`, `git` and `ssh` (Git for Windows has both). On Windows run scripts
with `py -I script.py …` (or `python`). Pick the backup folder with the student (default: next to their projects,
e.g. `F:\USYD-Projects\Canvas-Backup`) and a `.env` path outside it.

1. **Canvas token**: Canvas → Account → Settings → *Approved Integrations* → **+ New Access Token** (purpose
   "backup", expiry a week). Student puts `CANVAS_TOKEN=...` in `.env`.
2. **Ed token**: https://edstem.org/au/settings/api-tokens → create → `ED_TOKEN=...` in `.env`.
3. **SSH key for Ed git** (only needed for git-submitted assignments): if `~/.ssh/id_ed25519.pub` doesn't exist,
   run `ssh-keygen -t ed25519 -N "" -C "ed-backup" -f ~/.ssh/id_ed25519` (mention: no passphrase, so keep the
   private file private). Show the **public** key (`cat ~/.ssh/id_ed25519.pub`, on Windows also `| clip`) and have
   the student add it at Ed → Settings → SSH Keys. Never show or move the private key.

Quick check that both tokens work (prints the name and course count only):
`GET https://canvas.sydney.edu.au/api/v1/users/self` and `GET https://edstem.org/api/user`.

## Step 1 — Canvas

```
py -I scripts/canvas_backup.py --env <.env> --out <backup> --dry-run     # summary per course + total GB
py -I scripts/canvas_backup.py --env <.env> --out <backup>               # run in the background; can take an hour+
```

It walks every course: Home, Syllabus, Modules (files; pages saved as HTML with every embedded Canvas file
downloaded and re-linked for offline use), the Files area and Pages list when visible, pages that are only
linked from other pages (common: e.g. a hidden "Online resources" page), my submissions (all attempts), teacher
feedback files, rubric scores, assignment descriptions with their attached specs, and my personal files. Re-running
resumes (existing files with the same size are skipped) — so after fixing anything, just run it again.

Afterwards: read `_download-log.txt` (locked or deleted files are normal; a pattern of failures is not), list the
largest files and the `Other/` portal folders, and ask whether to drop staff datasets or portals the student
doesn't want. For courses with few materials, check `materials/links.md` and the course tabs: the content is
usually on Ed, Gradescope or an external site.

## Step 2 — Ed

```
py -I scripts/ed_backup.py --env <.env> --out <backup> --map-only   # check each Ed course → Canvas folder
py -I scripts/ed_backup.py --env <.env> --out <backup>              # background; Ed is slow (rate limits)
py -I scripts/ed_git_clone.py --out <backup>                        # needs the SSH key in Ed
py -I scripts/ed_browser_tasks.py --env <.env> --out <backup>       # writes <backup>/_ed-browser-tasks.md
```

Check the `--map-only` output before the real run: each Ed course should land in the matching term/course
folder (a course with no Canvas twin gets a new folder, which is fine). `ed_backup.py` saves lessons (document
slides → HTML with images, PDFs, quizzes with my answers) and, for every challenge I submitted to, a
`submissions.md` with times, tests passed and the latest feedback. `ed_git_clone.py` then pulls the full git
history for git-submission assignments — often the student's most valuable code (e.g. a C systems assignment
that only ever lived on Ed's git server).

What the API can't give: **Ed resources** (the file host needs the browser session) and **code of non-git
challenges** (only visible in the Submissions view). `ed_browser_tasks.py` turns those into an English
checklist for a browser agent or for the student. Part B (challenge code) takes roughly 2 hours per 300
challenges; offer `--assignments-only` or `--no-challenges`.

## Step 3 — Browser tasks and Gradescope

See `references/browser-tasks.md` for the texts to hand to Claude in Chrome (Ed checklist, Gradescope export,
optional login-protected maths notes). After the browser work:

```
py -I scripts/sort_downloads.py --downloads <Downloads> --out <backup> --since "YYYY-MM-DD HH:MM"         # dry run
py -I scripts/sort_downloads.py --downloads <Downloads> --out <backup> --since "YYYY-MM-DD HH:MM" --move
py -I scripts/gradescope_import.py --export "<Downloads>/Gradescope backup.zip" --out <backup>            # then --apply
```

Use the time just before the browser work started for `--since`, so older downloads are ignored. Look at the
unmatched list together with the student before deleting anything that isn't clearly a duplicate.

## Step 4 — Wrap up

Give the student a short summary table: per platform what was saved (counts, GB), what was deliberately
skipped, and anything still missing with the reason. Then remind them to:

1. revoke the Canvas token (Account → Settings → Approved Integrations) and the Ed token (Settings → API Tokens),
   and delete `.env` (offer to delete it — but only once they confirm they're finished);
2. optionally remove the Ed SSH key;
3. copy the backup folder to a second place they control (external drive or personal cloud — not uni OneDrive);
4. keep course materials private (copyright), and be careful before publishing any assignment code
   (academic integrity — courses reuse assignments).
