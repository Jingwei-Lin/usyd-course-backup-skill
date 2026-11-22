# Troubleshooting and things learned the hard way

**Ed returns 403 "error code: 1010".** Cloudflare blocks Python urllib's default User-Agent. Use `requests`
(as in Ed's official API sample at https://edstem.org/au/settings/api-tokens) — it sends its own honest UA.
Do not fake a browser User-Agent; that is evading bot protection and the permission system will (rightly) stop it.

**Ed returns 429.** Ed rate-limits aggressively. The scripts go one request at a time with back-off; never
parallelise Ed calls.

**Ed resources: 307 → static.edusercontent.com → 404.** The file host wants the browser's session cookie, not
the API token — even with the token it 404s. Don't keep probing; resources are a browser task.

**Ed git: "Permission denied (publickey)".** The SSH key isn't in Ed yet (Settings → SSH Keys).
**"git is not enabled for this challenge"** means that challenge never used git (or only self-test/viva
checkers do); its code is only in Ed's Submissions view → browser task. **"repository not found"** with no name
after the id means the path was wrong; use `challenge/<id>/<anything>`.

**Non-git challenge submissions have no code in the API.** `/api/challenges/submissions/<id>` returns
results, feedback, test counts and a `workspace_hash`, but no files. That's expected.

**Browser agent saved a JSON file containing `"ticket"` as `ed-<id>-submission.zip`.** It's a one-time
download ticket (a short-lived credential), not code — `sort_downloads.py` reports and deletes it.

**Canvas: "materials=0" for a course that clearly had content.** Usually the content is in Pages embedded in
Modules (handled), in pages linked only from other pages (handled by the linked-pages phase), on Ed
(run `ed_backup.py`), on Gradescope, or on an external site. Check `materials/links.md` and the course's tabs.

**Canvas Pages list returns 404.** Many courses hide the Pages tab from students; individual pages still load
by URL. That's why the script follows links instead of relying on the list.

**FileNotFoundError on Windows for a path that exists.** A name truncated to end in a space or dot — Windows
strips those. `clean()` strips them after truncating; keep that if you edit it.

**"Filename too long".** Deep `.venv`/`node_modules` paths in some repos; use `git -c core.longpaths=true`.

**Two copies of the same handout in two offerings** (e.g. INFO1110 2021 S2 and 2022 S1). Both get filed; the
browser names the second `name (1).pdf`, which `sort_downloads.py` handles.

**Huge staff datasets** (e.g. multi-GB zips in capstone course modules) are downloaded like everything else.
After the run, list the largest files (`find <backup> -size +500M`) and ask whether to keep them.

**Faculty portals** (Engineering/CS Student Portal, exam notification sites) are included by Canvas but are
rarely worth keeping; they end up under `Other/` and `<year>-Other/`. Offer to delete them.

**Outlook: Import/Export is greyed out.** Common for student Microsoft 365 accounts (licence state or tenant
settings). Check `HKCU\Software\Policies\Microsoft\Office\16.0\Outlook` for `DisablePST`; if absent, the object
model route still works — use `email_export_msg.ps1` / `email_export_pst.ps1`. Also check the student used File in
the main window, not inside an open message.

**Outlook: the export only has the last year of email.** Cached Exchange mode syncs a limited window. Set
"Download email for the past" to All and wait for the sync before exporting (the msg script's `-CheckOnly`
shows the oldest inbox date).

**Outlook: "A program is trying to access e-mail address information…"** That's Outlook's object-model guard;
the student clicks Allow (it may ask again after 10 minutes on machines without up-to-date antivirus).

**Outlook: `.ics` export fails with "You don't have appropriate permission".** That calendar is a subscription
(e.g. public holidays). Ignore it.

**Outlook: a test PST stays locked after `RemoveStore`.** Outlook holds the file until it's restarted; delete
leftovers after closing Outlook.

**The token got printed / pasted into chat.** Revoke it immediately and create a new one. The scripts never
print tokens; when inspecting `.env`, show only key names and lengths.
