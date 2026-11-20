# Build the distributable single-file exe.
# Usage:  powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
# Version: bump rc\__init__.py __version__ and assets\version_info.txt

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = $env:PYTHON
if (-not $py) {
    $dshPython = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $dshPython) { $py = $dshPython }
}
if (-not $py) { $py = "python" }
$appName = "Interpres"

Set-Location $root

Write-Host "Cleaning old build output..."
Remove-Item build, dist, "$appName.spec" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Building single-file exe (about 1 minute)..."
& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $appName `
    --icon "assets\reading-companion.ico" `
    --version-file "assets\version_info.txt" `
    --add-data "assets\reading-companion.ico;assets" `
    --add-data "rc\tts_script.ps1;rc" `
    --add-data "rc\tts_onecore.ps1;rc" `
    --add-data "rc\play_mp3.ps1;rc" `
    --collect-submodules lxml `
    --paths "$root\vendor_build" `
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
    app.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed" -ForegroundColor Red
    exit 1
}

$exe = Join-Path $root "dist\$appName.exe"
if (-not (Test-Path $exe)) {
    Write-Host "exe not found: $exe" -ForegroundColor Red
    exit 1
}

# 生成校验和（zip 内的 SHA256SUMS.txt 只含 exe；dist 里的还会追加 zip 哈希）
$sumFile = Join-Path $root "dist\SHA256SUMS.txt"
$exeHash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
Set-Content -Path $sumFile -Value ("$exeHash  $appName.exe") -Encoding ascii

# Pack a zip for sharing: exe + readme
$stage = Join-Path $env:TEMP "rc_package"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item $exe $stage
Copy-Item $sumFile $stage
$readmes = Get-ChildItem $root -Filter "*.txt" -File | Select-Object -First 1
if ($readmes) { Copy-Item $readmes.FullName $stage }
foreach ($extra in @("THIRD_PARTY_NOTICES.md", "README.md", "LICENSE")) {
    $path = Join-Path $root $extra
    if (Test-Path $path) { Copy-Item $path $stage }
}
$licenses = Join-Path $root "licenses"
if (Test-Path $licenses) { Copy-Item $licenses $stage -Recurse }
$docs = Join-Path $root "docs"
if (Test-Path $docs) { Copy-Item $docs $stage -Recurse }
$zip = Join-Path $root "dist\$appName.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue

$zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
Add-Content -Path $sumFile -Value ("$zipHash  $appName.zip")

$exeSize = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$zipSize = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host ("exe: " + $exe + "  " + $exeSize + " MB") -ForegroundColor Green
Write-Host ("zip: " + $zip + "  " + $zipSize + " MB") -ForegroundColor Green
