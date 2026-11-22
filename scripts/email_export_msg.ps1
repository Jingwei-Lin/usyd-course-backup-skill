# Read-only export of the student's university mailbox (Microsoft 365, via the classic Outlook desktop app):
#   every item -> .msg (Unicode, attachments included) in a mirrored folder tree,
#   every calendar -> .ics as well, plus index.csv (date, from, to, subject, attachments, file).
# Works even when File > Open & Export > Import/Export is greyed out. Nothing in the mailbox is changed.
# Resumable: items already exported (same file name) are skipped; delete the newest few files first if a run
# was interrupted mid-write.
#
# usage:  powershell -ExecutionPolicy Bypass -File email_export_msg.ps1 [-Out F:\USYD-Archive\Email] [-Store you@uni.sydney.edu.au] [-CheckOnly]
param([string]$Out = (Join-Path $HOME 'USYD-Archive\Email'), [string]$Store = '', [switch]$CheckOnly)

$ErrorActionPreference = 'Continue'
$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace('MAPI')
$st = if ($Store) { $ns.Stores | Where-Object { $_.DisplayName -eq $Store } } else { $ns.Stores | Where-Object { $_.DisplayName -like '*@uni.sydney.edu.au' } }
$st = $st | Select-Object -First 1
if (-not $st) { throw 'University mailbox not found in Outlook. Add the account in Outlook first, or pass -Store.' }
"mailbox: $($st.DisplayName)"

# Outlook's cached mode often keeps only the last 12 months locally; the export can only see what is synced.
$inbox = $ns.GetDefaultFolder(6); $items = $inbox.Items; $items.Sort('[ReceivedTime]')
$first = $items.GetFirst()
if ($first) { "inbox: {0} items, oldest {1:yyyy-MM-dd}" -f $items.Count, $first.ReceivedTime }
"(If the oldest date is only ~1 year ago, set File > Account Settings > the account > 'Download email for the past: All', restart Outlook and wait for 'All folders are up to date'.)"
if ($CheckOnly) { return }

$root = Join-Path $Out $st.DisplayName
New-Item -ItemType Directory -Force -Path $root | Out-Null
$errors = Join-Path $Out 'export-errors.txt'
$rows = New-Object System.Collections.Generic.List[object]
$sha = [System.Security.Cryptography.SHA1]::Create()
$script:done = 0; $script:skipped = 0; $script:failed = 0

function Clean([string]$s, [int]$max = 80) {
  if ([string]::IsNullOrWhiteSpace($s)) { $s = '(no subject)' }
  $s = ($s -replace '[<>:"/\\|?*\x00-\x1f]', '_').Trim()
  if ($s.Length -gt $max) { $s = $s.Substring(0, $max) }
  return $s.TrimEnd('. ')   # Windows drops trailing dots/spaces
}

function ItemDate($it) {
  foreach ($p in 'ReceivedTime', 'Start', 'CreationTime') { try { $d = $it.$p; if ($d -and $d.Year -gt 1900) { return $d } } catch {} }
  return Get-Date '2000-01-01'
}

function Export-Folder($folder, [string]$dir) {
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  if ($folder.DefaultItemType -eq 1) {   # calendar: one .ics with full details (subscribed calendars may refuse)
    try {
      $ex = $folder.GetCalendarExporter(); $ex.CalendarDetail = 2; $ex.IncludeAttachments = $true
      $ex.IncludePrivateDetails = $true; $ex.IncludeWholeCalendar = $true
      $ics = Join-Path $dir ((Clean $folder.Name) + '.ics'); if (-not (Test-Path -LiteralPath $ics)) { $ex.SaveAsICal($ics) }
    } catch { Add-Content $errors "ICS $($folder.FolderPath): $($_.Exception.Message)" }
  }
  $items = $folder.Items
  for ($i = 1; $i -le $items.Count; $i++) {
    try {
      $it = $items.Item($i); $d = ItemDate $it
      $subj = ''; try { $subj = $it.Subject } catch {}
      $id = ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($it.EntryID)) | Select-Object -First 4 | ForEach-Object { $_.ToString('x2') }) -join ''
      $path = Join-Path $dir ('{0:yyyy-MM-dd HHmm} - {1} [{2}].msg' -f $d, (Clean $subj), $id)
      if (Test-Path -LiteralPath $path) { $script:skipped++ } else { $it.SaveAs($path, 9); $script:done++ }   # 9 = Unicode .msg
      $from = ''; $to = ''; $att = 0
      try { $from = $it.SenderEmailAddress; if ($it.SenderName) { $from = "$($it.SenderName) <$from>" } } catch {}
      try { $to = $it.To } catch {}
      try { $att = $it.Attachments.Count } catch {}
      $rows.Add([pscustomobject]@{ Folder = $folder.FolderPath; Date = $d.ToString('yyyy-MM-dd HH:mm'); From = $from; To = $to;
                                   Subject = $subj; Attachments = $att; File = $path.Substring($Out.Length + 1) })
    } catch { $script:failed++; Add-Content $errors "ITEM $($folder.FolderPath) #$i : $($_.Exception.Message)" }
    if ((($script:done + $script:skipped) % 500) -eq 0) { "  progress: exported $script:done, skipped $script:skipped, failed $script:failed" }
  }
  foreach ($sub in $folder.Folders) { Export-Folder $sub (Join-Path $dir (Clean $sub.Name 60)) }
}

$t0 = Get-Date
foreach ($top in $st.GetRootFolder().Folders) { Export-Folder $top (Join-Path $root (Clean $top.Name 60)) }
$rows | Export-Csv -LiteralPath (Join-Path $Out 'index.csv') -NoTypeInformation -Encoding UTF8
"done in {0:N1} min: exported {1}, already present {2}, failed {3}; index rows {4}" -f ((Get-Date) - $t0).TotalMinutes, $script:done, $script:skipped, $script:failed, $rows.Count
