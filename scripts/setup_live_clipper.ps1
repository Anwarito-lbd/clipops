# ClipOps live clipper + auto-poster setup (Windows PowerShell)
#   powershell -ExecutionPolicy Bypass -File scripts\setup_live_clipper.ps1
#   options: -WhisperModels "tiny,small"   -Python "py -3.12"   -SkipFFmpeg
param(
    [string]$WhisperModels = "tiny,small",
    [string]$Python = "py -3.12",
    [switch]$SkipFFmpeg
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Python virtual environment (.venv)"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $exe, $pyArgs = $Python.Split(" ")
    & $exe @pyArgs -m venv .venv
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip wheel | Out-Null

Step "Python packages (streamlink, faster-whisper, Google OAuth, API stack)"
& $Py -m pip install -r apps\api\requirements.txt
& $Py -m pip install "streamlink>=6.0" "faster-whisper>=1.0.0" "google-auth-oauthlib>=1.2" "python-dotenv>=1.0"

Step "FFmpeg (with libass for burned captions)"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if ($SkipFFmpeg) { Write-Warning "ffmpeg missing; install it and re-run" }
    elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        Write-Warning "Open a NEW terminal after this script so ffmpeg is on PATH."
    } else { Write-Warning "Install ffmpeg (full build) from https://www.gyan.dev/ffmpeg/builds/ and add it to PATH" }
} else { Write-Host "ffmpeg found: $((Get-Command ffmpeg).Source)" }

Step "Pre-download Whisper models ($WhisperModels) so launch night doesn't wait on downloads"
foreach ($m in $WhisperModels.Split(",")) {
    & $Py -c "from faster_whisper import WhisperModel; WhisperModel('$($m.Trim())', device='cpu', compute_type='int8'); print('whisper $($m.Trim()) ready')"
}
& $Py -c "import torch; print('CUDA GPU:', torch.cuda.is_available())" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "(torch not installed: Whisper runs on CPU via CTranslate2; use --device cuda only with CUDA libs)" }

Step "Config files"
New-Item -ItemType Directory -Force -Path secrets | Out-Null
if (-not (Test-Path ".env")) { Copy-Item .env.example .env; Write-Host "created .env  -> fill in the keys" }
if (-not (Test-Path "accounts.json")) { Copy-Item workers\publisher\accounts.example.json accounts.json; Write-Host "created accounts.json -> review it" }

Step "Self-check"
& $Py -m workers.publisher doctor --accounts accounts.json
Write-Host "`nNext: fill .env, run the auth commands doctor lists, then:" -ForegroundColor Green
Write-Host "  .venv\Scripts\python.exe -m workers.live_clipper live --wave au --scout 3 --language en --profile gta6 --layout split --streamers workers\live_clipper\gta6_streamers.json --autopost accounts.json --autopost-dry-run"
