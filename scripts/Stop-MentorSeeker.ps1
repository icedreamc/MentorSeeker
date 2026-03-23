$ErrorActionPreference = 'Continue'

$ports = @(3000, 8000)
$targetPids = @()

foreach ($port in $ports) {
  try {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop |
      Select-Object -ExpandProperty OwningProcess -Unique
    $targetPids += $listeners
  }
  catch {
    # Ignore missing listeners / unsupported platforms.
  }
}

$targetPids = $targetPids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique

if (-not $targetPids -or $targetPids.Count -eq 0) {
  Write-Host '[MentorSeeker] No running frontend/backend processes found on ports 3000/8000.'
  exit 0
}

foreach ($procId in $targetPids) {
  try {
    Stop-Process -Id $procId -Force -ErrorAction Stop
    Write-Host "[MentorSeeker] Stopped process PID=$procId"
  }
  catch {
    Write-Warning "[MentorSeeker] Failed to stop PID=$procId : $($_.Exception.Message)"
  }
}

Write-Host '[MentorSeeker] Stop command finished.'
