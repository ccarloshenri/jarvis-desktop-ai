# Download the Silero VAD ONNX model (~1 MB) into models/vad/.
# Run from the repo root: powershell -ExecutionPolicy Bypass -File scripts/fetch_silero_vad.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelDir = Join-Path $RepoRoot "models/vad"
$ModelPath = Join-Path $ModelDir "silero_vad.onnx"
$Url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"

if (Test-Path $ModelPath) {
    Write-Host "silero_vad.onnx already present at $ModelPath — skipping." -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
Write-Host "Downloading Silero VAD from $Url" -ForegroundColor Cyan
Invoke-WebRequest -Uri $Url -OutFile $ModelPath -UseBasicParsing
$Size = (Get-Item $ModelPath).Length
Write-Host ("Saved {0} ({1} bytes)" -f $ModelPath, $Size) -ForegroundColor Green
