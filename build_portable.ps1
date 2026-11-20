# Build the portable folder release (avoids onefile %TEMP% extraction).
# Usage: powershell -ExecutionPolicy Bypass -File .\build_portable.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendor = Join-Path $root "vendor"
if (-not (Test-Path -LiteralPath $vendor)) { $vendor = Join-Path $root "vendor_build" }
$py = $env:PYTHON
if (-not $py) {
    $dshPython = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $dshPython) { $py = $dshPython }
}
if (-not $py) { $py = "python" }
$appName = "Interpres"

Set-Location $root

Write-Host "Cleaning old portable output..."
Remove-Item build_portable, dist_portable -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Building portable folder (about 1 minute)..."
& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name $appName `
    --icon "assets\reading-companion.ico" `
    --version-file "assets\version_info.txt" `
    --add-data "assets\reading-companion.ico;assets" `
    --add-data "rc\tts_script.ps1;rc" `
    --add-data "rc\tts_onecore.ps1;rc" `
    --add-data "rc\play_mp3.ps1;rc" `
    --collect-submodules lxml `
    --paths "$vendor" `
    --hidden-import pystray `
    --hidden-import pystray._win32 `
    --hidden-import rc.dict_profiles `
    --hidden-import rc.dict_profile_editor `
    --hidden-import rc.prompts_en `
    --hidden-import rc.language_dialog `
    --hidden-import rc.anki_card_settings `
    --hidden-import rc.wordbook_anki_settings `
    --hidden-import edge_tts `
    --hidden-import aiohttp `
    --collect-submodules edge_tts `
    --collect-submodules aiohttp `
    --collect-data certifi `
    --exclude-module numpy `
    --exclude-module PIL._avif `
    --distpath "$root\dist_portable" `
    --workpath "$root\build_portable" `
    app.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed" -ForegroundColor Red
    exit 1
}

$built = Join-Path $root "dist_portable\$appName"
$exe = Join-Path $built "$appName.exe"
if (-not (Test-Path $exe)) {
    Write-Host "exe not found: $exe" -ForegroundColor Red
    exit 1
}

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null

$stage = Join-Path $env:TEMP "rc_portable_package"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item (Join-Path $built "*") $stage -Recurse
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $stage
Copy-Item (Join-Path $root "README.md") $stage
Copy-Item (Join-Path $root "LICENSE") $stage
# Copy the Chinese quick-start without naming it literally: PS 5.1 decodes
# BOM-less scripts as ANSI, so a CJK literal here silently matches nothing.
Get-ChildItem -LiteralPath $root -File -Filter "*.txt" |
    Where-Object { $_.Name -notlike "requirements*" } |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName $stage }
if (Test-Path (Join-Path $root "licenses")) { Copy-Item (Join-Path $root "licenses") $stage -Recurse }
if (Test-Path (Join-Path $root "docs")) { Copy-Item (Join-Path $root "docs") $stage -Recurse }

$exeHash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
Set-Content -Path (Join-Path $stage "SHA256SUMS.txt") -Value ("$exeHash  $appName.exe") -Encoding ascii

$zip = Join-Path $dist "$appName.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue

$zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
$distSum = Join-Path $dist "SHA256SUMS.txt"
Set-Content -Path $distSum -Value ("$exeHash  $appName.exe") -Encoding ascii
Add-Content -Path $distSum -Value ("$zipHash  $appName.zip")

$zipSize = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host ("portable folder: " + $built) -ForegroundColor Green
Write-Host ("zip: " + $zip + "  " + $zipSize + " MB") -ForegroundColor Green
