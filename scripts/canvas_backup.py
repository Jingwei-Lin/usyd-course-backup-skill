"""Read-only Canvas backup for a University of Sydney student.

Saves, per course, into <out>/<YYYY-Sn>/<COURSE>/:
  materials/   module files and pages (as HTML with their embedded files downloaded and re-linked), the
               course Home page and Syllabus, the Files area (if visible), the Pages list (if visible),
               pages that are only linked from other pages (_linked-pages/), external links (links.md)
  submissions/ my submitted files (every attempt), text submissions, teacher feedback files, and each
               assignment's description/spec with the files it links
  feedback.md  score, rubric and comments for every assignment
and at the top level: README.md (index), grades.csv, _personal-files/ (my Canvas "My Files"),
_download-log.txt, _protected-links.json (files on login-protected uni websites, e.g. maths.usyd.edu.au).

The token is read from the env file and never printed. Re-running is safe: files already present with the
same size are skipped, so an interrupted run can simply be started again.

usage:
  python canvas_backup.py --env .env --out Canvas-Backup [--dry-run] [--no-linked-pages]
"""
import argparse, csv, glob, html, json, os, re, sys, threading, time
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

HOST = "canvas.sydney.edu.au"
API = f"https://{HOST}/api/v1"
TOKEN, OUT, DRY = "", "", False
lock = threading.Lock()
stats = {"files": 0, "bytes": 0, "skipped": 0, "errors": 0}
log_lines, grade_rows, index_rows, jobs = [], [], [], []
FILE_LINK = re.compile(r'(href|src)="([^"]*?/(?:courses/(\d+)/)?files/(\d+)[^"]*)"')
PAGE_LINK = re.compile(r'/courses/(\d+)/pages/([^"#?\s<>]+)')
PROTECTED = re.compile(r'href="(https?://(?:www\.)?maths\.usyd\.edu\.au/[^"]*/priv/[^"]+)"')


def read_env(path):
    return {k.strip(): v.strip().strip('"\'') for k, v in
            (l.split("=", 1) for l in open(path, encoding="utf-8") if "=" in l and not l.lstrip().startswith("#"))}


def log(msg):
    with lock:
        log_lines.append(msg)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_noredir = urllib.request.build_opener(_NoRedirect)


def request(url, auth=True, follow=True, tries=6):
    headers = {"Authorization": f"Bearer {TOKEN}"} if auth else {}
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            return (urllib.request.urlopen if follow else _noredir.open)(req, timeout=120)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and not follow:
                return e
            body = e.read(300).decode("utf-8", "replace") if e.fp else ""
            if (e.code == 403 and "Rate Limit" in body) or e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** i)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(2 ** i)
    raise RuntimeError(f"giving up on {url.split('?')[0]}")


def get_json(path):
    with request(f"{API}{path}") as r:
        return json.load(r)


def get_all(path):
    url = path if path.startswith("http") else f"{API}{path}{'&' if '?' in path else '?'}per_page=100"
    items = []
    while url:
        with request(url) as r:
            data = json.load(r)
            items += data if isinstance(data, list) else [data]
            m = re.search(r'<([^>]+)>; rel="next"', r.headers.get("Link", ""))
            url = m.group(1) if m else None
    return items


def safe_get_all(path, what):
    """Students often get 401/403/404 for hidden tabs (Files, Pages); that's normal, not an error."""
    try:
        return get_all(path)
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403, 404):
            log(f"HTTP {e.code} listing {what}")
        return None


def clean(name, limit=90):
    """Safe Windows file name. Windows silently drops trailing dots/spaces, so strip them after truncating."""
    name = html.unescape(str(name or "untitled"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    if len(name) > limit:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: limit - len(ext) - 1].rstrip(". ") + "." + ext) if dot and len(ext) <= 8 else name[:limit]
    return name.strip().rstrip(". ") or "untitled"


def unique(path, taken):
    base, ext = os.path.splitext(path)
    n, p = 2, path
    while p.lower() in taken:
        p, n = f"{base} ({n}){ext}", n + 1
    taken.add(p.lower())
    return p


def term_folder(c):
    """USYD course codes/terms look like '2023_S1C_COMP2017_ND', 'Semester 1 2025' or '2024 Semester 2'."""
    code, term = str(c.get("course_code") or c.get("name") or ""), str((c.get("term") or {}).get("name") or "")
    m = re.search(r"(20\d\d)_S([12])", code)
    if m:
        return f"{m.group(1)}-S{m.group(2)}"
    m = re.search(r"Semester ([12]) (20\d\d)", term) or re.search(r"(20\d\d) Semester ([12])", term)
    if m:
        a, b = m.groups()
        return f"{a}-S{b}" if len(a) == 4 else f"{b}-S{a}"
    m = re.search(r"(20\d\d)", code + " " + term)
    return f"{m.group(1)}-Other" if m else "Other"


def course_folder(c):
    """'COMP4349 COMP5349 (ND)' -> 'COMP4349-COMP5349'; exam sites -> 'INFO1113 Final Exam'; portals keep their name."""
    code = str(c.get("course_code") or c.get("name") or "")
    codes = list(dict.fromkeys(re.findall(r"[A-Z]{4}\d{4}", code)))
    if not codes:
        return clean(c.get("name") or code, 60)
    if "FINALEXAM" in code.replace(" ", "").upper():
        return codes[0] + " Final Exam"
    if "Thesis" in code:
        return clean(code, 60)
    return "-".join(codes[:2])


def course_dirs(courses):
    used, out = set(), {}
    for c in sorted(courses, key=lambda c: (term_folder(c), course_folder(c))):
        if c.get("access_restricted_by_date"):
            continue
        rel = os.path.join(term_folder(c), course_folder(c))
        if rel.lower() in used:
            rel = os.path.join(term_folder(c), f"{course_folder(c)} ({c['id']})")
        used.add(rel.lower())
        out[c["id"]] = rel
    return out


def queue(url, dest, size):
    if os.path.exists(dest) and size and os.path.getsize(dest) == size:
        with lock:
            stats["skipped"] += 1
        return
    jobs.append((url, dest, size))


def download(job):
    url, dest, size = job
    try:
        # Canvas file URLs carry a verifier and redirect to signed storage: never send the token off Canvas
        r = request(url, auth=urllib.parse.urlparse(url).hostname == HOST, follow=False)
        loc = r.headers.get("Location") if getattr(r, "code", 200) in (301, 302, 303, 307, 308) else None
        resp = request(loc, auth=urllib.parse.urlparse(loc).hostname == HOST) if loc else r
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with resp, open(dest + ".part", "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        os.replace(dest + ".part", dest)
        with lock:
            stats["files"] += 1
            stats["bytes"] += os.path.getsize(dest)
    except Exception as e:
        log(f"FAILED {os.path.relpath(dest, OUT)}: {type(e).__name__} {getattr(e, 'code', '')}")
        with lock:
            stats["errors"] += 1


def file_meta(fid, cid=None):
    try:
        return get_json(f"/{'courses/%s/' % cid if cid else ''}files/{fid}")
    except urllib.error.HTTPError as e:
        return {"_error": e.code}


def write_text(path, text):
    if DRY:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


def save_html(cid, title, body, path, files_dir, taken, got_ids):
    """Write a page as HTML; download every Canvas file it links or embeds and point the link at the local copy,
    so the saved page works offline. Returns how many files it references."""
    local = {}

    def repl(m):
        attr, link_cid, fid = m.group(1), m.group(3) or cid, m.group(4)
        if fid not in local:
            meta = file_meta(fid, link_cid)
            if "_error" in meta and str(link_cid) != str(cid):
                meta = file_meta(fid, cid)
            if "_error" in meta or meta.get("locked_for_user") or not meta.get("url"):
                log(f"EMBEDDED FILE UNAVAILABLE in '{title}': file {fid} ({meta.get('_error', 'locked')})")
                local[fid] = None
            else:
                if meta["id"] in got_ids:
                    dest = got_ids[meta["id"]]
                else:
                    dest = unique(os.path.join(files_dir, clean(meta.get("display_name"))), taken)
                    got_ids[meta["id"]] = dest
                    queue(meta["url"], dest, meta.get("size"))
                local[fid] = dest
        if not local[fid]:
            return m.group(0)
        return f'{attr}="{os.path.relpath(local[fid], os.path.dirname(path)).replace(os.sep, "/")}"'

    body = FILE_LINK.sub(repl, body or "")
    write_text(path, f"<!doctype html><meta charset=utf-8><title>{html.escape(title or '')}</title>"
                     f"<h1>{html.escape(title or '')}</h1>\n{body}")
    return len([v for v in local.values() if v])


def materials(c, cdir, ctx):
    cid, got_ids, taken, n, links = c["id"], ctx["got"], ctx["taken"], 0, []
    mat = os.path.join(cdir, "materials")
    for title, path in (("Home", f"/courses/{cid}/front_page"), ("Syllabus", f"/courses/{cid}?include[]=syllabus_body")):
        try:
            d = get_json(path)
            if title == "Home":
                ctx["known_pages"].add(d.get("url"))
            body = d.get("body") if title == "Home" else d.get("syllabus_body")
            if body and body.strip():
                n += save_html(cid, f"{c.get('name')} — {title}", body, os.path.join(mat, f"00 {title}.html"),
                               os.path.join(mat, f"00 {title} files"), taken, got_ids)
                ctx["bodies"].append((body, os.path.join(mat, f"00 {title}.html")))
        except Exception:
            pass
    for mi, m in enumerate(safe_get_all(f"/courses/{cid}/modules?include[]=items", "modules") or [], 1):
        mdir = os.path.join(mat, clean(f"{mi:02d} {m.get('name')}", 80))
        for it in m.get("items") or safe_get_all(f"/courses/{cid}/modules/{m['id']}/items", "module items") or []:
            t = it.get("type")
            if t == "File":
                meta = file_meta(it["content_id"], cid)
                if "_error" in meta or meta.get("locked_for_user") or not meta.get("url"):
                    log(f"LOCKED/UNAVAILABLE {course_folder(c)} / {m.get('name')} / {it.get('title')}")
                    continue
                if meta["id"] not in got_ids:
                    dest = unique(os.path.join(mdir, clean(meta.get("display_name"))), taken)
                    got_ids[meta["id"]] = dest
                    queue(meta["url"], dest, meta.get("size"))
                    n += 1
            elif t == "Page":
                ctx["known_pages"].add(it.get("page_url"))
                try:
                    pg = get_json(f"/courses/{cid}/pages/{it['page_url']}")
                    p = unique(os.path.join(mdir, clean(it.get("title"), 80) + ".html"), taken)
                    n += save_html(cid, pg.get("title"), pg.get("body"), p, mdir, taken, got_ids)
                    ctx["bodies"].append((pg.get("body") or "", p))
                except Exception as e:
                    log(f"PAGE UNAVAILABLE {course_folder(c)} / {it.get('title')} ({type(e).__name__})")
            elif t in ("ExternalUrl", "ExternalTool"):
                links.append(f"- [{m.get('name')}] {it.get('title')}: {it.get('external_url') or it.get('html_url')}")
    if links:
        write_text(os.path.join(mat, "links.md"), "# External links in modules\n\n" + "\n".join(links) + "\n")
    files = safe_get_all(f"/courses/{cid}/files", "files") or []
    if files:  # only some courses show the Files area to students
        folders = {f["id"]: f["full_name"] for f in (safe_get_all(f"/courses/{cid}/folders", "folders") or [])}
        for f in files:
            if f["id"] in got_ids or f.get("locked_for_user") or not f.get("url"):
                continue
            rel = folders.get(f.get("folder_id"), "course files").split("/")[1:]
            dest = unique(os.path.join(mat, "_files-area", *[clean(x, 60) for x in rel], clean(f.get("display_name"))), taken)
            got_ids[f["id"]] = dest
            queue(f["url"], dest, f.get("size"))
            n += 1
    for pg in safe_get_all(f"/courses/{cid}/pages", "pages") or []:
        if pg.get("url") in ctx["known_pages"]:
            continue
        ctx["known_pages"].add(pg.get("url"))
        try:
            full = get_json(f"/courses/{cid}/pages/{pg['url']}")
            p = unique(os.path.join(mat, "_pages", clean(pg.get("title"), 80) + ".html"), taken)
            n += save_html(cid, full.get("title"), full.get("body"), p, os.path.join(mat, "_pages", "files"), taken, got_ids)
            ctx["bodies"].append((full.get("body") or "", p))
        except Exception:
            pass
    return n


def linked_pages(c, cdir, ctx):
    """Pages that aren't in Modules and aren't listed (Pages tab hidden) but are linked from saved pages,
    e.g. MATH1021's 'online-resources'. Follow links breadth-first within the same course."""
    cid, n = c["id"], 0
    todo = [s for body, _ in ctx["bodies"] for lc, s in PAGE_LINK.findall(body) if int(lc) == cid]
    for body, where in ctx["bodies"]:
        for u in PROTECTED.findall(body):
            ctx["protected"][u] = os.path.relpath(where, OUT)
    seen = set(ctx["known_pages"])
    while todo:
        slug = urllib.parse.unquote(todo.pop())
        if slug in seen:
            continue
        seen.add(slug)
        try:
            pg = get_json(f"/courses/{cid}/pages/{urllib.parse.quote(slug)}")
        except Exception:
            log(f"LINKED PAGE UNAVAILABLE {course_folder(c)} / {slug}")
            continue
        body = pg.get("body") or ""
        todo += [s for lc, s in PAGE_LINK.findall(body) if int(lc) == cid]
        out = unique(os.path.join(cdir, "materials", "_linked-pages", clean(pg.get("title") or slug, 80) + ".html"), ctx["taken"])
        n += save_html(cid, pg.get("title"), body, out, os.path.join(cdir, "materials", "_linked-pages", "files"),
                       ctx["taken"], ctx["got"])
        for u in PROTECTED.findall(body):
            ctx["protected"][u] = os.path.relpath(out, OUT)
    return n


def fmt_date(s):
    return s.replace("T", " ")[:16] + " UTC" if s else "—"


def submissions(c, cdir, term, cname):
    cid = c["id"]
    subs = safe_get_all(f"/courses/{cid}/students/submissions?student_ids[]=self&include[]=submission_comments"
                        f"&include[]=rubric_assessment&include[]=submission_history&include[]=assignment", "submissions") or []
    taken, md, n = set(), [], 0
    subs.sort(key=lambda s: ((s.get("assignment") or {}).get("due_at") or "9999", (s.get("assignment") or {}).get("name") or ""))
    for s in subs:
        a = s.get("assignment") or {}
        adir = os.path.join(cdir, "submissions", clean(a.get("name") or f"assignment {s.get('assignment_id')}", 70))
        attempts = [h for h in (s.get("submission_history") or [s]) if h and (h.get("submitted_at") or h.get("attachments"))]
        multi = len({h.get("attempt") for h in attempts}) > 1
        for h in attempts:
            d = os.path.join(adir, f"attempt-{h.get('attempt')}") if multi else adir
            for att in h.get("attachments") or []:
                queue(att["url"], unique(os.path.join(d, clean(att.get("display_name"))), taken), att.get("size"))
                n += 1
            if h.get("body"):
                write_text(os.path.join(d, "text-submission.html"), h["body"])
        if (a.get("description") or "").strip():
            save_html(cid, a.get("name"), a["description"], os.path.join(adir, "assignment-description.html"),
                      os.path.join(adir, "spec-files"), taken, {})
        for cm in s.get("submission_comments") or []:
            for att in cm.get("attachments") or []:
                queue(att["url"], unique(os.path.join(adir, "feedback-files", clean(att.get("display_name"))), taken), att.get("size"))
        pts, score = a.get("points_possible"), s.get("score")
        grade_rows.append({"term": term, "course": cname, "assignment": a.get("name"), "due": a.get("due_at"),
                           "submitted": s.get("submitted_at"), "score": score, "points_possible": pts,
                           "grade": s.get("grade"), "late": s.get("late"), "missing": s.get("missing"), "excused": s.get("excused")})
        sec = [f"## {a.get('name')}", "", f"- **Due:** {fmt_date(a.get('due_at'))}  ",
               f"- **Submitted:** {fmt_date(s.get('submitted_at'))}{' (late)' if s.get('late') else ''}"
               f"{' (missing)' if s.get('missing') else ''}  ",
               f"- **Score:** {score if score is not None else '—'} / {pts if pts is not None else '—'}"
               f"{'  (grade: ' + str(s.get('grade')) + ')' if s.get('grade') not in (None, str(score)) else ''}"]
        if s.get("url"):
            sec.append(f"- **Submitted URL:** {s['url']}")
        rubric, ra = {r["id"]: r for r in a.get("rubric") or []}, s.get("rubric_assessment") or {}
        if ra:
            sec += ["", "| Criterion | Points | Comment |", "|---|---|---|"]
            for crit_id, v in ra.items():
                crit = rubric.get(crit_id, {})
                sec.append(f"| {(crit.get('description') or crit_id).replace('|', '/')} | {v.get('points', '—')} / "
                           f"{crit.get('points', '—')} | {(v.get('comments') or '').replace(chr(10), ' ').replace('|', '/')} |")
        for cm in s.get("submission_comments") or []:
            sec += ["", f"> **{cm.get('author_name')}** — {fmt_date(cm.get('created_at'))}  ",
                    *[f"> {line}" for line in (cm.get("comment") or "").splitlines()]]
        md.append("\n".join(sec))
    if md:
        write_text(os.path.join(cdir, "feedback.md"), f"# {c.get('name')} — scores and feedback\n\n" + "\n\n".join(md) + "\n")
    return n, len(subs)


def personal_files():
    folders = {f["id"]: f["full_name"] for f in (safe_get_all("/users/self/folders", "personal folders") or [])}
    taken = set()
    for f in safe_get_all("/users/self/files", "personal files") or []:
        if f.get("url"):
            rel = folders.get(f.get("folder_id"), "my files").split("/")[1:]
            queue(f["url"], unique(os.path.join(OUT, "_personal-files", *[clean(x, 60) for x in rel],
                                                clean(f.get("display_name"))), taken), f.get("size"))


def write_index():
    with open(os.path.join(OUT, "grades.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(grade_rows[0]) if grade_rows else ["term"])
        w.writeheader()
        w.writerows(grade_rows)
    rows = [r for r in index_rows if r[3] or r[4] or r[5]]
    lines = ["# Canvas backup — University of Sydney", "",
             f"Downloaded from {HOST} on {time.strftime('%Y-%m-%d')}: my own submissions, scores and feedback, my "
             "personal Canvas files, and the course materials available to me. Course materials are the University's "
             "and teaching staff's copyright — for personal reference only, do not republish.", "",
             "Per-assignment scores are in `grades.csv`; each course folder has a `feedback.md`.", "",
             "| Term | Course | Canvas name | Material files | Submitted files | Assignments | Final score | Final grade |",
             "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {t} | [{cn}]({urllib.parse.quote(t + '/' + cn)}/) | {(nm or '').replace('|', '/')} | {m} | {sf} | {na} | "
              f"{fs if fs is not None else '—'} | {fg or '—'} |" for t, cn, nm, m, sf, na, fs, fg in rows]
    lines += ["", "`_personal-files/` holds my own Canvas uploads. Download problems are listed in `_download-log.txt`."]
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    open(os.path.join(OUT, "_download-log.txt"), "w", encoding="utf-8").write("\n".join(sorted(log_lines)) + "\n")


def main():
    global TOKEN, OUT, DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True, help="file containing CANVAS_TOKEN=...")
    ap.add_argument("--out", required=True, help="backup root folder, e.g. Canvas-Backup")
    ap.add_argument("--dry-run", action="store_true", help="list what would be downloaded; write nothing")
    ap.add_argument("--no-linked-pages", action="store_true", help="skip following links to unlisted pages")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    TOKEN, OUT, DRY = read_env(args.env)["CANVAS_TOKEN"], os.path.abspath(args.out), args.dry_run

    courses = get_all("/courses?include[]=term&include[]=total_scores&state[]=available&state[]=completed")
    dirs, protected = course_dirs(courses), {}
    for c in sorted(courses, key=lambda c: dirs.get(c["id"], "")):
        if c["id"] not in dirs:
            log(f"RESTRICTED course {c.get('id')}")
            continue
        rel = dirs[c["id"]]
        cdir, term, cname = os.path.join(OUT, rel), *rel.split(os.sep, 1)
        before = len(jobs)
        ctx = {"got": {}, "taken": set(), "known_pages": set(), "bodies": [], "protected": protected}
        mat = materials(c, cdir, ctx)
        if not args.no_linked_pages:
            mat += linked_pages(c, cdir, ctx)
        sub_files, n_asg = submissions(c, cdir, term, cname)
        enr = next((e for e in c.get("enrollments") or [] if e.get("type") == "student"), {})
        index_rows.append((term, cname, c.get("name"), mat, sub_files, n_asg,
                           enr.get("computed_final_score"), enr.get("computed_final_grade")))
        print(f"{rel:40} materials={mat:4} submitted_files={sub_files:3} assignments={n_asg:3} queued={len(jobs) - before}", flush=True)
    personal_files()
    total = sum(j[2] or 0 for j in jobs)
    print(f"\nqueued {len(jobs)} downloads ({total / 1e9:.2f} GB), already present {stats['skipped']}, "
          f"login-protected external files found {len(protected)}")
    if DRY:
        return
    with ThreadPoolExecutor(args.workers) as ex:
        for i, _ in enumerate(ex.map(download, jobs), 1):
            if i % 100 == 0:
                print(f"  {i}/{len(jobs)} done ({stats['bytes'] / 1e9:.2f} GB)", flush=True)
    os.makedirs(OUT, exist_ok=True)
    write_index()
    json.dump([{"url": u, "found_on": p} for u, p in sorted(protected.items())],
              open(os.path.join(OUT, "_protected-links.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"done: downloaded {stats['files']} files ({stats['bytes'] / 1e9:.2f} GB), skipped {stats['skipped']}, "
          f"errors {stats['errors']}, log entries {len(log_lines)} (see _download-log.txt)")


if __name__ == "__main__":
    main()
