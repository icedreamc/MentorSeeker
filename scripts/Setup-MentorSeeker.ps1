param(
  [switch]$ForceInstall
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$venvDir = Join-Path $backendDir 'venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$backendEnv = Join-Path $backendDir '.env'
$frontendEnv = Join-Path $frontendDir '.env.local'

function Assert-Command {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$Hint
  )

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing command '$Name'. $Hint"
  }
}

Write-Host '[MentorSeeker] Checking system dependencies...'
Assert-Command -Name 'python' -Hint 'Please install Python 3.10+ and enable PATH.'
Assert-Command -Name 'npm' -Hint 'Please install Node.js 20+ (includes npm).'

if (-not (Test-Path $venvPython)) {
  Write-Host '[MentorSeeker] Creating backend virtual environment...'
  & python -m venv $venvDir
}

Write-Host '[MentorSeeker] Installing backend dependencies...'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $backendDir 'requirements.txt')

$nodeModules = Join-Path $frontendDir 'node_modules'
if ($ForceInstall -or -not (Test-Path $nodeModules)) {
  Write-Host '[MentorSeeker] Installing frontend dependencies...'
  Push-Location $frontendDir
  try {
    & npm install
  }
  finally {
    Pop-Location
  }
} else {
  Write-Host '[MentorSeeker] Frontend dependencies already installed. Use -ForceInstall to reinstall.'
}

if (-not (Test-Path $frontendEnv)) {
  Write-Host '[MentorSeeker] Creating frontend/.env.local ...'
  Set-Content -Path $frontendEnv -Encoding UTF8 -Value 'NEXT_PUBLIC_API_BASE=http://localhost:8000'
}

if (-not (Test-Path $backendEnv)) {
  Write-Host '[MentorSeeker] Creating backend/.env template ...'
  $backendEnvLines = @(
    'DATABASE_URL=sqlite:///./mentorseeker.db',
    'LLM_BASE_URL=',
    'LLM_API_KEY=',
    'LLM_MODEL=gpt-5-mini',
    'PROVIDER_EMAIL=',
    'BROWSER_COOKIE=',
    'USER_PROFILE_TEXT_B64=',
    'USER_LIBRARY_SUMMARY_B64='
  )
  Set-Content -Path $backendEnv -Encoding UTF8 -Value $backendEnvLines
}

Write-Host '[MentorSeeker] Setup completed successfully.'
