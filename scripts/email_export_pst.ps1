# Copy the student's university mailbox into a new PST (Outlook data file) and verify item counts per folder.
# A PST opens in any Outlook and can be imported into another mailbox later. Folders are COPIED (never moved)
# from the mailbox into the new PST; the PST is detached from Outlook again at the end. Works even when
# File > Open & Export > Import/Export is greyed out, as long as PSTs aren't blocked by policy (the script stops
# with a clear message if they are — fall back to email_export_msg.ps1).
#
# usage:  powershell -ExecutionPolicy Bypass -File email_export_pst.ps1 [-Pst F:\USYD-Archive\Email\uni-mailbox.pst] [-Store you@uni.sydney.edu.au]
param([string]$Pst = (Join-Path $HOME 'USYD-Archive\Email\uni-mailbox.pst'), [string]$Store = '')

$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace('MAPI')
$src = if ($Store) { $ns.Stores | Where-Object { $_.DisplayName -eq $Store } } else { $ns.Stores | Where-Object { $_.DisplayName -like '*@uni.sydney.edu.au' } }
$src = $src | Select-Object -First 1
if (-not $src) { throw 'University mailbox not found in Outlook. Add the account in Outlook first, or pass -Store.' }
if (Test-Path -LiteralPath $Pst) { throw "$Pst already exists - choose another name or delete it first" }
New-Item -ItemType Directory -Force -Path (Split-Path $Pst) | Out-Null
try { $ns.AddStoreEx($Pst, 2) } catch { throw "Outlook refused to create a PST (probably blocked by policy): $($_.Exception.Message)" }   # 2 = Unicode
$dst = $ns.Stores | Where-Object { $_.FilePath -eq $Pst } | Select-Object -First 1
$dstRoot = $dst.GetRootFolder()
try { $dstRoot.Name = "$($src.DisplayName) (backup $(Get-Date -Format yyyy-MM-dd))" } catch {}

function Count($f) { $n = 0; try { $n = $f.Items.Count } catch {}; foreach ($s in $f.Folders) { $n += Count $s }; return $n }

"copying $($src.DisplayName) -> $Pst"
$report = @()
foreach ($top in $src.GetRootFolder().Folders) {
  $want = Count $top
  if ($want -eq 0) { continue }                            # empty system folders are skipped
  $t0 = Get-Date
  try { $copy = $top.CopyTo($dstRoot); $got = Count $copy; $status = if ($got -eq $want) { 'OK' } else { 'MISMATCH' } }
  catch { $got = 0; $status = 'FAILED: ' + $_.Exception.Message }
  $line = '{0,-24} mailbox={1,6} pst={2,6}  {3}  ({4:N0}s)' -f $top.Name, $want, $got, $status, ((Get-Date) - $t0).TotalSeconds
  $line; $report += $line
}
$ns.RemoveStore($dstRoot)
Start-Sleep -Seconds 3
'PST size: {0:N2} GB  -> {1}' -f ((Get-Item -LiteralPath $Pst).Length / 1GB), $Pst
$report | Set-Content -LiteralPath ([IO.Path]::ChangeExtension($Pst, '.verify.txt')) -Encoding UTF8
