# Browser tasks (for Claude in Chrome or doing it by hand)

Some things can only be fetched from a logged-in browser session. Hand the student these task texts (English,
because browser agents follow English instructions most reliably). Everything goes to the normal Downloads
folder; the scripts file it afterwards. Remind them: browser downloads go to Downloads and can't be
redirected per file by the agent — that's why the scripts sort by name and size.

## 1. Ed resources and non-git challenge code

`scripts/ed_browser_tasks.py` writes the exact checklist to `<backup>/_ed-browser-tasks.md` (Part A: resources
with each course's Resources page URL; Part B: one direct link per challenge with my submissions). Give the
agent that file. Part B is slow (about two hours for ~300 challenges) — offer `--assignments-only` or
`--no-challenges` if the student only wants the important bits. When the agent is done, run
`sort_downloads.py`.

## 2. Gradescope export

Gradescope has no student API. Give the agent this text:

> Back up my Gradescope work (read-only — don't submit, regrade-request or change anything).
> 1. Open https://www.gradescope.com/account and sign in through "School Credentials" → University of Sydney.
> 2. For every course on the dashboard (including older terms — check "See older courses"), open each
>    assignment/quiz/exam that has a submission of mine and download:
>    - the **graded** copy (the "Download Graded Copy" button) — save as `<Assignment name> (graded).pdf`
>    - for programming/online assignments, the **original submission** ("Download Submission") — save as
>      `<Assignment name> (original).zip` (or the original file name if it isn't a zip)
> 3. Put the files in one folder per course named exactly as the course is shown on Gradescope, all inside a
>    folder called `Gradescope backup`, plus an `index.csv` with the columns
>    `Course, Assignment, Score, Type, File in ZIP, Size KB, Status, Gradescope link`
>    (Type = graded/original, Status = saved/failed). Zip it as `Gradescope backup.zip` in Downloads.
> 4. Skip entries with no submission; mention them in index.csv with Status "no submission".

Then: `python scripts/gradescope_import.py --export "<Downloads>/Gradescope backup.zip" --out <backup>` (dry
run), check the mapping, re-run with `--apply`. If a course is empty on Gradescope (e.g. only an empty "Final"),
write a one-line `gradescope/README.md` saying so, so nobody later thinks it was missed.

## 3. Login-protected university website files (optional)

`canvas_backup.py` records links to files on login-protected University sites (e.g. the School of Mathematics'
`www.maths.usyd.edu.au/.../priv/...` lecture notes linked from MATH1xxx Canvas pages) in
`<backup>/_protected-links.json`. Ask the student whether they want them — first-year maths notes are often not
worth the time. If yes, turn that JSON into a checklist like the Ed one (one section per course, one line per
file, save with the original name, prefix `<COURSE>-` only when two files share a name) and file the results
into `<course>/resources-maths-website/`.
