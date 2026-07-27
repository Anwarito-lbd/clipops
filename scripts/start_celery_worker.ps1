# Start Celery worker (requires Redis ping + CELERY_EAGER=false in .env)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:Path = "C:\Program Files\Redis;" + $env:Path
try {
  $pong = & redis-cli ping 2>$null
  if ($pong -ne "PONG") { throw "no pong" }
} catch {
  Write-Host "Starting redis-server..."
  Start-Process -FilePath "C:\Program Files\Redis\redis-server.exe" -WindowStyle Hidden
  Start-Sleep 2
}
Set-Location (Join-Path $root "apps\api")
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$root;$PWD"
$env:CELERY_EAGER = "false"
Write-Host "Celery worker (set CELERY_EAGER=false in .env for API too)"
celery -A app.celery_app.celery worker --loglevel=info --concurrency=1 --pool=solo
