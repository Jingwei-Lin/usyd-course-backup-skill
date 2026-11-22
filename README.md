# usyd-course-backup

A [Claude Code](https://claude.com/claude-code) skill that backs up a University of Sydney student's own
coursework from **Canvas**, **Ed** and **Gradescope**, and their **university email**, before their student
account closes.

It produces one folder tree, organised by term and course:

```
Canvas-Backup/
├─ README.md, grades.csv              index of all courses + every assignment's score
├─ 2023-S1/COMP2017/
│  ├─ materials/                      Canvas modules, pages (offline HTML), Home, Syllabus, hidden linked pages
│  ├─ submissions/                    my submitted files (every attempt), feedback files, assignment specs
│  ├─ feedback.md                     scores, rubrics, teacher comments
│  ├─ ed/                             Ed lessons, quizzes, resources, submission history, git assignment code
│  └─ gradescope/                     graded copies and original submissions
└─ _personal-files/                   my Canvas "My Files"
```

## What it saves

| Platform | Automatically (API) | Via a browser checklist |
|---|---|---|
| Canvas | submissions (all attempts), scores, rubrics, comments, feedback files, assignment specs, module files, pages with embedded files, hidden linked pages, Home/Syllabus, Files area, personal files | — |
| Ed | lessons (slides → HTML, PDFs, images), quizzes with my answers, submission records for every challenge, full git history of git-submitted assignments | course resources, code of non-git challenges |
| Gradescope | — | graded PDFs and original submissions (export), filed into each course |
| University email (@uni.sydney.edu.au) | every email with attachments as `.msg` + `index.csv`, calendars as `.ics`, and a verified PST — via the Outlook desktop app, even when Import/Export is greyed out | — |

The browser parts produce English task lists that can be handed to Claude in Chrome (or done by hand); a script
then files the downloads into the right course folders.

## Install

```bash
git clone https://github.com/Jingwei-Lin/usyd-course-backup-skill ~/.claude/skills/usyd-course-backup
pip install requests
```

Then in Claude Code just ask, for example: *"Back up all my Canvas and Ed courses before I graduate."*
Claude walks you through creating the tokens and runs everything.

Requirements: Python 3.9+, `requests`, `git` and `ssh` (Git for Windows includes both).

## Running the scripts yourself

```bash
# .env (keep it outside any repository):
#   CANVAS_TOKEN=...   Canvas → Account → Settings → Approved Integrations → New Access Token
#   ED_TOKEN=...       https://edstem.org/au/settings/api-tokens
python scripts/canvas_backup.py   --env .env --out Canvas-Backup --dry-run
python scripts/canvas_backup.py   --env .env --out Canvas-Backup
python scripts/ed_backup.py       --env .env --out Canvas-Backup --map-only
python scripts/ed_backup.py       --env .env --out Canvas-Backup
python scripts/ed_git_clone.py    --out Canvas-Backup              # SSH key added in Ed → Settings → SSH Keys
python scripts/ed_browser_tasks.py --env .env --out Canvas-Backup  # writes _ed-browser-tasks.md
python scripts/sort_downloads.py  --downloads ~/Downloads --out Canvas-Backup --since "YYYY-MM-DD HH:MM" --move
python scripts/gradescope_import.py --export "Gradescope backup.zip" --out Canvas-Backup --apply

# University email (classic Outlook for Windows, signed in to the uni account; keep Outlook open)
powershell -ExecutionPolicy Bypass -File scripts/email_export_msg.ps1 -Out D:\USYD-Archive\Email -CheckOnly
powershell -ExecutionPolicy Bypass -File scripts/email_export_msg.ps1 -Out D:\USYD-Archive\Email
powershell -ExecutionPolicy Bypass -File scripts/email_export_pst.ps1 -Pst D:\USYD-Archive\Email\uni-mailbox.pst
```

All scripts are read-only towards Canvas/Ed, never print tokens, send each token only to its own platform, and
can be re-run safely (existing files are skipped).

## Please note

- Course materials are the University's and teaching staff's copyright. Keep the backup for personal use; don't
  republish it. Be careful before publishing assignment code — courses reuse assignments.
- Revoke your Canvas and Ed tokens when you're done, and keep a second copy of the backup somewhere you control
  (not the university OneDrive — it closes with your account).
- Ed's API is provided "as is" and may change; see `references/troubleshooting.md` if something breaks.

## License

MIT — see [LICENSE](LICENSE).
