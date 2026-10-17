$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create virtual environment.' }
}
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$node = (Get-Command node -ErrorAction Stop).Source
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name YouTubeMP3 --version-file version_info.txt --icon "assets\app-icon.ico" --add-data "assets;assets" --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all imageio_ffmpeg --collect-all tkinterdnd2 --collect-all customtkinter --add-binary "${node};tools" app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath 'README.md' -Destination 'dist\YouTubeMP3\README.md' -Force
$appVersion = & $python -c "from app import VERSION; print(VERSION)"
if ($LASTEXITCODE -ne 0) { throw 'Version lookup failed.' }
New-Item -ItemType Directory -Path outputs -Force | Out-Null
$archivePath = Join-Path $PSScriptRoot "outputs\YouTubeMP3-$appVersion-win-x64.zip"
Compress-Archive -LiteralPath 'dist\YouTubeMP3' -DestinationPath $archivePath -Force
Write-Host "Package: $archivePath"
Write-Host 'Ready: dist\YouTubeMP3\YouTubeMP3.exe'
