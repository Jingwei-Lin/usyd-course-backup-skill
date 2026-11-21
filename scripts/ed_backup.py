"""Read-only Ed (edstem.org, AU region) backup into each course's `ed/` folder inside the Canvas backup.

Saves per course into <out>/<YYYY-Sn>/<COURSE>/ed/:
  lessons/<NN module>/<NN lesson>/   document slides as HTML (images saved locally), PDF slides, links,
                                     quizzes with my responses (.quiz.md)
  submissions/<lesson>/<challenge>/  submissions.md + submissions.json for every challenge I submitted to
                                     (times, tests passed, status, latest feedback/build output), challenge.html
and writes <out>/_ed-git-challenges.json — the list of challenges for ed_git_clone.py.

Resources cannot be downloaded through the API with a token (Ed's file host wants the browser session);
use ed_browser_tasks.py to produce a checklist for the browser instead.

Uses `requests` exactly like Ed's official API sample (honest User-Agent; Ed's Cloudflare blocks
urllib's default one). The token is sent only to edstem.org and never printed. Re-running is safe.

usage:
  python ed_backup.py --env .env --out Canvas-Backup [--map-only] [--dry-run]
"""
import argparse, html, json, os, re, sys, time
import requests

API = "https://edstem.org/api"
OUT, DRY = "", False
s = requests.Session()          # authenticated: edstem.org only
cdn = requests.Session()        # public CDN for slide PDFs/images: never gets the token
log, stats, git_list = [], {"files": 0, "bytes": 0, "skipped": 0}, []


def read_env(path):
    return {k.strip(): v.strip().strip('"\'') for k, v in
            (l.split("=", 1) for l in open(path, encoding="utf-8") if "=" in l and not l.lstrip().startswith("#"))}


def init(env_path, out, dry=False):
    global OUT, DRY
    s.headers["Authorization"] = "Bearer " + read_env(env_path)["ED_TOKEN"]
    OUT, DRY = os.path.abspath(out), dry


def get(path, **kw):
    """Ed rate-limits hard (HTTP 429): go one request at a time and back off."""
    for i in range(9):
        try:
            r = s.get(API + path, timeout=90, **kw)
        except requests.RequestException:
            time.sleep(2 ** i)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(90, 2 ** i))
            continue
        time.sleep(0.3)
        return r
    raise RuntimeError(f"giving up on {path}")


def getj(path):
    r = get(path)
    return r.json() if r.ok else None


def clean(name, limit=80):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", html.unescape(str(name or "untitled"))).strip()
    if len(name) > limit:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: limit - len(ext) - 1].rstrip(". ") + "." + ext) if dot and len(ext) <= 8 else name[:limit]
    return name.strip().rstrip(". ") or "untitled"


def write(path, text):
    if DRY:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        stats["skipped"] += 1
        return True
    if DRY:
        stats["files"] += 1
        return True
    for i in range(6):
        try:
            r = cdn.get(url, timeout=300, stream=True)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** i)
                continue
            if not r.ok:
                log.append(f"HTTP {r.status_code} {os.path.relpath(dest, OUT)}")
                return False
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest + ".part", "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            os.replace(dest + ".part", dest)
            stats["files"] += 1
            stats["bytes"] += os.path.getsize(dest)
            return True
        except requests.RequestException:
            time.sleep(2 ** i)
    log.append(f"FAILED {os.path.relpath(dest, OUT)}")
    return False


def _pair_tags(body):
    """Ed closes headings and lists with generic </heading> and </list>; give each the matching HTML end tag."""
    out, stack, pos = [], [], 0
    for m in re.finditer(r'<heading level="(\d)">|</heading>|<list style="(\w+)"[^>]*>|</list>', body):
        out.append(body[pos:m.start()])
        tok = m.group(0)
        if tok.startswith("<heading"):
            stack.append(f"h{m.group(1)}")
            out.append(f"<h{m.group(1)}>")
        elif tok.startswith("<list"):
            stack.append("ol" if m.group(2) == "number" else "ul")
            out.append(f"<{stack[-1]}>")
        else:
            out.append(f"</{stack.pop() if stack else 'p'}>")
        pos = m.end()
    return "".join(out) + body[pos:]


TAGS = [(r"<document[^>]*>", ""), (r"</document>", ""), (r"<paragraph>", "<p>"), (r"</paragraph>", "</p>"),
        (r"<list-item>", "<li>"), (r"</list-item>", "</li>"),
        (r"<bold>", "<b>"), (r"</bold>", "</b>"), (r"<italic>", "<i>"), (r"</italic>", "</i>"),
        (r"<underline>", "<u>"), (r"</underline>", "</u>"), (r"<snippet[^>]*>", "<pre>"), (r"</snippet>", "</pre>"),
        (r"<break\s*/?>", "<br>"), (r'<link href="([^"]*)"[^>]*>', r'<a href="\1">'), (r"</link>", "</a>"),
        (r'<callout type="([^"]*)"[^>]*>', r'<div class="callout \1">'), (r"</callout>", "</div>"),
        (r"<math>", '<span class="math">'), (r"</math>", "</span>")]


def ed_to_html(xml, title, folder):
    """Ed stores slides as its own XML; turn it into readable HTML and save its images next to it."""
    body = _pair_tags(xml or "")
    for pat, rep in TAGS:
        body = re.sub(pat, rep, body)

    def img(m):
        url = m.group(1)
        if "edusercontent.com" not in url:
            return m.group(0)
        name = clean(url.rstrip("/").split("/")[-1].split("?")[0], 60)
        name += "" if os.path.splitext(name)[1] else ".png"
        download(url, os.path.join(folder, "_images", name))
        return f'src="_images/{name}"'

    body = re.sub(r'src="([^"]+)"', img, body)
    return (f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title><style>body{{font-family:sans-serif;"
            f"max-width:900px;margin:2em auto}}pre{{background:#f4f4f4;padding:8px}}.callout{{border-left:4px solid #888;"
            f"padding:4px 12px}}img{{max-width:100%}}</style><h1>{html.escape(title)}</h1>\n{body}")


def ed_to_text(xml):
    t = re.sub(r"<break\s*/?>|</paragraph>|</list-item>|</heading>", "\n", xml or "")
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


def term_of(c):
    m = re.search(r"Semester ([12])", str(c.get("session") or ""))
    return f"{c.get('year')}-S{m.group(1)}" if m and str(c.get("year", "")).isdigit() else None


def course_dir(c):
    """Match an Ed course to the Canvas backup's course folder (same term + course code); create one if missing.
    Ed codes look like 'COMP2017 9017', 'SOFT2412/COMP9412', 'DATA2x02', '2025 CS UG Honours Thesis'."""
    term, text = term_of(c), f"{c.get('code')} {c.get('name')}"
    if "Thesis" in text and term:
        tdir = os.path.join(OUT, term)
        hits = [d for d in (os.listdir(tdir) if os.path.isdir(tdir) else []) if "Thesis" in d]
        return os.path.join(tdir, hits[0] if hits else "Honours Thesis")
    codes = [x.replace("x", "0") for x in re.findall(r"[A-Z]{4}\d[\dx]\d\d", text)]
    if not term or not codes:
        return None                                   # faculty portals etc.
    tdir = os.path.join(OUT, term)
    if os.path.isdir(tdir):
        for d in sorted(os.listdir(tdir)):
            if "Final Exam" not in d and any(code in d for code in codes):
                return os.path.join(tdir, d)
    return None if "Exam" in text else os.path.join(tdir, codes[0])


def backup_course(c, cdir, me):
    cid, ed = c["id"], os.path.join(cdir, "ed")
    n_slides = n_subs = 0
    lj = getj(f"/courses/{cid}/lessons") or {}
    mods = {m["id"]: m for m in lj.get("modules", [])}
    order = {mid: i for i, mid in enumerate(sorted(mods, key=lambda k: (mods[k].get("index") or 0, k)), 1)}
    lessons = sorted(lj.get("lessons", []), key=lambda l: (order.get(l.get("module_id"), 0), l.get("index") or 0, l["id"]))
    for li, l in enumerate(lessons, 1):
        mod = mods.get(l.get("module_id"))
        mfolder = clean(f"{order[mod['id']]:02d} {mod.get('name')}", 60) if mod else "00 No module"
        lfolder = os.path.join(ed, "lessons", mfolder, clean(f"{li:02d} {l.get('title')}", 70))
        d = (getj(f"/lessons/{l['id']}?view=1") or {}).get("lesson") or {}
        for si, sl in enumerate(sorted(d.get("slides") or [], key=lambda x: x.get("index") or 0), 1):
            base, t = os.path.join(lfolder, clean(f"{si:02d} {sl.get('title') or sl['type']}", 70)), sl["type"]
            n_slides += 1
            if t == "pdf" and sl.get("file_url"):
                download(sl["file_url"], base + ".pdf")
            elif t in ("webpage", "video") and (sl.get("url") or sl.get("video_url")):
                write(base + ".url", f"[InternetShortcut]\nURL={sl.get('url') or sl.get('video_url')}\n")
            elif t == "quiz":
                qs = (getj(f"/lessons/slides/{sl['id']}/questions") or {}).get("questions", [])
                mine = {r.get("question_id"): r for r in (getj(f"/lessons/slides/{sl['id']}/questions/responses") or {}).get("responses", [])}
                md = [f"# {sl.get('title') or 'Quiz'}", ""]
                for qi, q in enumerate(qs, 1):
                    dq = q.get("data") or {}
                    md += [f"## Question {qi}", "", ed_to_text(dq.get("content")), ""]
                    for ai, ans in enumerate(dq.get("answers") or []):
                        md.append(f"- ({ai}) {ed_to_text(ans) if isinstance(ans, str) else ans}{' ✔' if ai in (dq.get('solution') or []) else ''}")
                    r = mine.get(q.get("id"))
                    if r:
                        ok = {True: " — correct", False: " — incorrect"}.get(r.get("correct"), "")
                        md += ["", f"**My response:** `{json.dumps(r.get('data'), ensure_ascii=False)}`{ok}"]
                    md.append("")
                write(base + ".quiz.md", "\n".join(md))
            elif sl.get("content"):
                write(base + ".html", ed_to_html(sl["content"], sl.get("title") or l.get("title") or "", lfolder))
            if not sl.get("challenge_id"):
                continue
            subs = (getj(f"/users/{me}/challenges/{sl['challenge_id']}/submissions") or {}).get("submissions", [])
            if not subs:
                continue
            n_subs += len(subs)
            sdir = os.path.join(ed, "submissions", clean(l.get("title"), 50), clean(sl.get("title") or t, 50))
            ch = (getj(f"/challenges/{sl['challenge_id']}") or {}).get("challenge") or {}
            is_git = bool((ch.get("features") or {}).get("git_submission") or (ch.get("settings") or {}).get("only_git_submission"))
            rows = [f"# {sl.get('title')} — my submissions", "", f"Lesson: {l.get('title')}  ",
                    f"Challenge id: {sl['challenge_id']}{' (git submission)' if is_git else ''}  ",
                    f"Ed page: https://edstem.org/au/courses/{cid}/lessons/{l['id']}/slides/{sl['id']}", "",
                    "| # | Submitted | Tests passed | Status | Git head |", "|---|---|---|---|---|"]
            for k, sb in enumerate(sorted(subs, key=lambda x: x["created_at"]), 1):
                rows.append(f"| {k} | {sb['created_at'][:19].replace('T', ' ')} | {sb.get('testcase_pass_count')}/"
                            f"{sb.get('testcase_total_count')} | {sb.get('status') or ''} | {(sb.get('git_head') or '')[:10]} |")
            full = (getj(f"/challenges/submissions/{max(subs, key=lambda x: x['created_at'])['id']}") or {}).get("submission") or {}
            res = full.get("result") or {}
            fb = ((res.get("feedback") or "") + "\n" + ((res.get("build") or {}).get("output") or "")).strip()
            if fb:
                rows += ["", "## Latest submission feedback", "", "```", fb[:20000], "```"]
            write(os.path.join(sdir, "submissions.md"), "\n".join(rows) + "\n")
            write(os.path.join(sdir, "submissions.json"), json.dumps(subs, ensure_ascii=False, indent=1))
            if ch.get("content"):
                write(os.path.join(sdir, "challenge.html"), ed_to_html(ch["content"], ch.get("title") or "", sdir))
            git_list.append({"dir": os.path.join(sdir, "code"), "challenge_id": sl["challenge_id"], "course_id": cid,
                             "lesson_id": l["id"], "slide_id": sl["id"], "lesson": l.get("title"),
                             "title": ch.get("title") or sl.get("title"), "git": is_git, "submissions": len(subs)})
    return n_slides, n_subs


def ed_courses():
    u = getj("/user")
    return u["user"]["id"], sorted((e["course"] for e in u["courses"]), key=lambda c: (str(c.get("year")), str(c.get("session"))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True, help="file containing ED_TOKEN=...")
    ap.add_argument("--out", required=True, help="the Canvas backup root (Ed goes into each course's ed/ folder)")
    ap.add_argument("--map-only", action="store_true", help="only print which folder each Ed course maps to")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    init(args.env, args.out, args.dry_run)
    me, courses = ed_courses()
    for c in courses:
        cdir = course_dir(c)
        label = f"{str(c.get('code'))[:28]:28} {c.get('year')} {str(c.get('session'))[:10]:10}"
        if not cdir:
            print(f"skip   {label} (portal / exam site / no course code)")
            continue
        if args.map_only:
            print(f"map    {label} -> {os.path.relpath(cdir, OUT)}{'' if os.path.isdir(cdir) else '   (new folder)'}")
            continue
        try:
            n_sl, n_sub = backup_course(c, cdir, me)
            print(f"done   {os.path.relpath(cdir, OUT):40} slides={n_sl:5} my_submissions={n_sub:5}", flush=True)
        except Exception as ex:
            log.append(f"ERROR course {c.get('code')}: {type(ex).__name__} {ex}")
            print(f"ERROR  {c.get('code')}: {ex}")
    if args.map_only:
        return
    write(os.path.join(OUT, "_ed-git-challenges.json"), json.dumps(git_list, ensure_ascii=False, indent=1))
    if log:
        write(os.path.join(OUT, "_ed-download-log.txt"), "\n".join(log) + "\n")
    print(f"\nlesson files downloaded: {stats['files']} ({stats['bytes'] / 1e9:.2f} GB), skipped {stats['skipped']}, "
          f"problems {len(log)}; challenges with my submissions: {len(git_list)} "
          f"(git-enabled: {sum(1 for g in git_list if g['git'])}) -> next: ed_git_clone.py, ed_browser_tasks.py")


if __name__ == "__main__":
    main()
