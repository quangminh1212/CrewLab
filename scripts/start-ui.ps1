#Requires -Version 5.1
<#
.SYNOPSIS
  Start CrewLab Messenger chat UI detached (survives closing agent terminals).

.EXAMPLE
  powershell -File C:\Dev\CrewLab\scripts\start-ui.ps1
  powershell -File C:\Dev\CrewLab\scripts\start-ui.ps1 -Port 8765 -Spec examples\multi-cli-room
#>
param(
  [string]$Spec = "examples\multi-cli-room",
  [int]$Port = 8765,
  [string]$HostAddr = "127.0.0.1",
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$specPath = if ([IO.Path]::IsPathRooted($Spec)) { $Spec } else { Join-Path $Root $Spec }
if (-not (Test-Path $specPath)) {
  throw "crew-spec not found: $specPath"
}

# Free port if a dead listener is stuck (best-effort)
try {
  Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
      $pid = $_.OwningProcess
      if ($pid -and $pid -gt 0) {
        Write-Host "Stopping old listener PID $pid on :$Port"
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
      }
    }
} catch {}

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) { $pyCmd = Get-Command py -ErrorAction SilentlyContinue }
if (-not $pyCmd) { throw "python not on PATH" }
$py = $pyCmd.Source

$args = @("-m", "crewlab", "ui", $specPath, "--host", $HostAddr, "--port", "$Port")
if ($NoBrowser) { $args += "--no-browser" }

$logDir = Join-Path $Root "runs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "ui-$Port.out.log"
$errLog = Join-Path $logDir "ui-$Port.err.log"

$p = Start-Process -FilePath $py `
  -ArgumentList $args `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog `
  -PassThru

Start-Sleep -Seconds 1
$url = "http://${HostAddr}:$Port/"
Write-Host "CrewLab UI started PID=$($p.Id)"
Write-Host "  URL:  $url"
Write-Host "  Spec: $specPath"
Write-Host "  Logs: $outLog"
Write-Host "  Stop: Stop-Process -Id $($p.Id)"

if (-not $NoBrowser) {
  try { Start-Process $url } catch {}
}

# quick health
try {
  $h = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 3
  Write-Host "  Health: $($h.Content)"
} catch {
  Write-Host "  Health: (warming up) $_"
}
