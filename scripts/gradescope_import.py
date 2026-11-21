"""Put a Gradescope export (made in the browser, see references/browser-tasks.md) into each course's
gradescope/ folder in the backup. Gradescope has no student API, so the export is a folder or zip shaped like:

  Gradescope backup/
    index.csv                         Course, Assignment, Score, Type, File in ZIP, Size KB, Status, Gradescope link
    <Gradescope course name>/<Assignment> (graded).pdf | (original).zip

Gradescope course names vary ("COMP2022-2922, S2 2023", "2023_S1C_COMP2123_ND", "COMP5046 - 2026",
"2026_S1C_COMP5310_NE_FINALEXAM"); they're matched to backup folders by course code and year. Exam sites go
into gradescope/Final Exam/. Prints the mapping; copies only with --apply (the export itself is left untouched).

usage:
  python gradescope_import.py --export "Gradescope backup.zip" --out Canvas-Backup [--apply]
"""
import argparse, glob, io, os, re, shutil, sys, zipfile

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--export", required=True, help="the export zip or folder")
ap.add_argument("--out", required=True)
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")

if zipfile.is_zipfile(args.export):
    z = zipfile.ZipFile(args.export)
    entries = [(i.filename, (lambda i=i: z.read(i))) for i in z.infolist() if not i.filename.endswith("/")]
else:
    root = os.path.dirname(os.path.abspath(args.export.rstrip("/\\")))
    entries = [(os.path.relpath(p, root).replace(os.sep, "/"), (lambda p=p: open(p, "rb").read()))
               for p in glob.glob(os.path.join(args.export, "**", "*"), recursive=True) if os.path.isfile(p)]

folders = [d for d in glob.glob(os.path.join(args.out, "20*", "*")) if os.path.isdir(d) and "Final Exam" not in d]


def target(gs_course):
    codes = set(re.findall(r"[A-Z]{4}\d{4}", gs_course))
    years = re.findall(r"20\d\d", gs_course)
    sem = re.search(r"_S([12])|\bS([12])\b|Semester ([12])", gs_course)
    hits = [d for d in folders if codes & set(re.findall(r"[A-Z]{4}\d{4}", os.path.basename(d)))]
    if years:
        hits = [d for d in hits if os.path.basename(os.path.dirname(d)).startswith(years[0])] or hits
    if sem and len(hits) > 1:
        n = next(g for g in sem.groups() if g)
        hits = [d for d in hits if os.path.basename(os.path.dirname(d)).endswith(f"S{n}")] or hits
    return hits[0] if len(hits) == 1 else None


plan, unknown = [], set()
for name, read in entries:
    parts = name.split("/")
    if parts[-1].lower() == "index.csv":
        plan.append((read, os.path.join(args.out, "_gradescope-index.csv"), "index"))
        continue
    if len(parts) < 3:
        continue
    gs_course = parts[-2]
    t = target(gs_course)
    if not t:
        unknown.add(gs_course)
        continue
    sub = "Final Exam" if "FINALEXAM" in gs_course.replace(" ", "").upper() else ""
    plan.append((read, os.path.join(t, "gradescope", sub, parts[-1]), gs_course))

for gs in sorted({k for *_, k in plan if k != "index"}):
    dest = next(os.path.dirname(d) for _, d, k in plan if k == gs)
    print(f"{gs:45} -> {os.path.relpath(dest, args.out)}  ({sum(1 for *_, k in plan if k == gs)} files)")
for u in sorted(unknown):
    print(f"{u:45} -> ?? no matching course folder (create it or rename the export folder to include the course code)")
if not args.apply:
    print("\ndry run — re-run with --apply to copy")
    sys.exit()
for read, dest, _ in plan:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(read())
print(f"copied {len(plan)} files")
