param(
  [switch]$SkipInstall,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$setupScript = Join-Path $PSScriptRoot 'Setup-MentorSeeker.ps1'
$venvPython = Join-Path $repoRoot 'backend\venv\Scripts\python.exe'

if (-not $SkipInstall) {
  & $setupScript
}

if (-not (Test-Path $venvPython)) {
  throw "Backend python not found at: $venvPython. Please run Setup-MentorSeeker.ps1 first."
}

$backendCmd = "Set-Location '$repoRoot'; & '$venvPython' -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000"
$frontendCmd = "Set-Location '$repoRoot\\frontend'; `$env:NEXT_PUBLIC_API_BASE='http://localhost:8000'; npm run dev"

Write-Host '[MentorSeeker] Launching backend on http://localhost:8000 ...'
Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $backendCmd | Out-Null

Start-Sleep -Seconds 1
Write-Host '[MentorSeeker] Launching frontend on http://localhost:3000 ...'
Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $frontendCmd | Out-Null

if (-not $NoBrowser) {
  Start-Sleep -Seconds 2
  Start-Process 'http://localhost:3000' | Out-Null
}

Write-Host '[MentorSeeker] Started. Use Stop-MentorSeeker.ps1 to stop services.'
