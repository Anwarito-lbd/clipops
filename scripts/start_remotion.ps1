# Start ClipOps Remotion overlay service (port 3100)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location (Join-Path $root "templates")
if (-not (Test-Path "node_modules")) { npm install }
$env:PORT = "3100"
Write-Host "Remotion on http://127.0.0.1:3100"
node server.js
