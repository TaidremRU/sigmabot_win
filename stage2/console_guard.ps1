# Возврат сессии alex на физическую консоль после ОТКЛЮЧЕНИЯ RDP.
# Триггер: задача SigmaConsoleGuard по событию TS LocalSessionManager 24/40.
# Ничего не делает, если alex уже на консоли или активно сидит по RDP.
$ErrorActionPreference = 'SilentlyContinue'
Start-Sleep -Seconds 2

$id = $null
$act = $false
foreach ($ln in (qwinsta 2>$null)) {
    if ($ln -notmatch '\balex\b') { continue }
    foreach ($t in ($ln -split '\s+')) { if ($t -match '^\d+$') { $id = $t; break } }
    $hasConsole = $ln -match '(?i)\bconsole\b'
    $hasRdp     = $ln -match '(?i)rdp-tcp#'
    if (-not $hasConsole -and -not $hasRdp) { $act = $true }   # сессия отключена
}

$log = "$PSScriptRoot\console_guard.log"
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
if ($act -and $id) {
    $out = & tscon $id /dest:console 2>&1
    "$stamp tscon $id /dest:console -> rc=$LASTEXITCODE $out" | Out-File $log -Append -Encoding utf8
} else {
    "$stamp no-op (id=$id act=$act)" | Out-File $log -Append -Encoding utf8
}
