# Bring up local Operator stack helpers: Redis + Remotion (API/dashboard separate)
$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:Path = "C:\Program Files\Redis;" + $env:Path

Write-Host "== Redis =="
try {
  if ((redis-cli ping) -ne "PONG") { throw "down" }
  Write-Host "Redis already up"
} catch {
  Start-Process -FilePath "C:\Program Files\Redis\redis-server.exe" -WindowStyle Hidden
  Start-Sleep 2
  redis-cli ping
}

Write-Host "== Remotion =="
try {
  Invoke-RestMethod "http://127.0.0.1:3100/health" -TimeoutSec 2 | Out-Null
  Write-Host "Remotion already up"
} catch {
  Start-Process powershell -ArgumentList "-NoExit", "-File", (Join-Path $PSScriptRoot "start_remotion.ps1")
  Write-Host "Started Remotion in a new window"
}

Write-Host ""
Write-Host "Next:"
Write-Host "  API:      cd apps\api; .\.venv\Scripts\activate; `$env:PYTHONPATH='..\..\..;`$PWD'; uvicorn app.main:app --reload --port 8000"
Write-Host "  Dashboard: cd apps\dashboard; npm run dev"
Write-Host "  Optional async: set CELERY_EAGER=false in .env, then scripts\start_celery_worker.ps1"
Write-Host "  Optional diarization: set HF_TOKEN in .env (Hugging Face token with pyannote access)"
