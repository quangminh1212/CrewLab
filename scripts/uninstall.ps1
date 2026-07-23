#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Hermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }
$SkillsSrc = Join-Path $Root 'skills'
$SkillsDstRoot = Join-Path $Hermes 'skills'

Write-Host "== CrewLab detach ==" -ForegroundColor Cyan

Get-ChildItem $SkillsSrc -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  $dst = Join-Path $SkillsDstRoot $_.Name
  if (Test-Path $dst) {
    $item = Get-Item $dst -Force
    $isLink = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    if ($isLink) {
      cmd /c "rmdir `"$dst`"" | Out-Null
      Write-Host "Removed junction: $dst"
    } else {
      Write-Host "Skip non-junction: $dst" -ForegroundColor Yellow
    }
  }
}

$note = Join-Path $Hermes 'crewlab-HERMES.md'
if (Test-Path $note) {
  Remove-Item $note -Force
  Write-Host "Removed $note"
}

Write-Host "OK. CrewLab detached." -ForegroundColor Green
