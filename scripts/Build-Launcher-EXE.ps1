$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcherPy = Join-Path $repoRoot 'launcher\MentorSeekerLauncher.py'
$distDir = Join-Path $repoRoot 'dist'
$buildDir = Join-Path $repoRoot 'build'
$specFile = Join-Path $repoRoot 'MentorSeekerLauncher.spec'
$releaseDir = Join-Path $repoRoot 'releases'
$targetExe = Join-Path $releaseDir 'MentorSeekerLauncher.exe'

if (-not (Test-Path $launcherPy)) {
  throw "Launcher source not found: $launcherPy"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python command not found. Please install Python 3.10+ first."
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

Write-Host '[MentorSeeker] Installing/Updating PyInstaller ...'
& python -m pip install --upgrade pyinstaller

Write-Host '[MentorSeeker] Building MentorSeekerLauncher.exe ...'
& python -m PyInstaller --noconfirm --onefile --windowed --name MentorSeekerLauncher $launcherPy

$builtExe = Join-Path $distDir 'MentorSeekerLauncher.exe'
if (-not (Test-Path $builtExe)) {
  throw "Build failed: $builtExe not found"
}

Copy-Item -Path $builtExe -Destination $targetExe -Force

# Keep root tidy after packaging.
if (Test-Path $distDir) { Remove-Item $distDir -Recurse -Force }
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
if (Test-Path $specFile) { Remove-Item $specFile -Force }

Write-Host "[MentorSeeker] Build done: $targetExe"
Write-Host '[MentorSeeker] You can now double-click releases\MentorSeekerLauncher.exe'
