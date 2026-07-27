# One-command local helpers: Redis + Remotion, then print API/dashboard commands
$ErrorActionPreference = "Continue"
& (Join-Path $PSScriptRoot "start_stack.ps1")

Write-Host ""
Write-Host "=== To hit 99% go-live score ===" -ForegroundColor Cyan
Write-Host "1. Start API + dashboard (see README)"
Write-Host "2. Sign in → Home shows Go-live score + next 3 steps"
Write-Host "3. Chrome → Load unpacked: browser-extension/"
Write-Host "4. On Content Rewards (logged in): Scan → Approve → Join yourself"
Write-Host "5. Upload real footage → Review preview → Approve → Download"
Write-Host "6. Post on TikTok yourself → Mark posted → Submit on CR → Mark submitted"
Write-Host "7. Next day: enter views in Tracking (closes learning)"
Write-Host ""
Write-Host "Optional polish: HF_TOKEN for diarization; CELERY_EAGER=false for async"
Write-Host "Score API: GET /api/operator/readiness"
