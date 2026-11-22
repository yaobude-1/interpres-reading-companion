param(
    [string]$AppDir = $PSScriptRoot,
    [switch]$Startup,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$AppDir = (Resolve-Path -LiteralPath $AppDir).Path
$App = Join-Path $AppDir 'app.py'
$RunVbs = Join-Path $AppDir 'run.vbs'
$Desktop = [Environment]::GetFolderPath('Desktop')
$Link = Join-Path $Desktop 'Interpres.lnk'
$StartupDir = [Environment]::GetFolderPath('Startup')
$StartupLink = Join-Path $StartupDir 'Interpres.lnk'

if ($Uninstall) {
    $uninstaller = Join-Path $AppDir 'uninstall.ps1'
    if (Test-Path -LiteralPath $uninstaller) {
        & $uninstaller -AppDir $AppDir -KeepData
        return
    }
    foreach ($p in @($Link, $StartupLink)) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
    }
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$App*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    Write-Host '已删除快捷方式并退出程序（数据目录 ~\.reading-companion 保留）。'
    return
}

if (-not (Test-Path -LiteralPath $App)) {
    throw "找不到 app.py：$App"
}

# ---- 找一个可用的 pythonw.exe：优先 DSH 自带运行时 ----
$candidates = @(
    (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'),
    (Get-Command pythonw.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
)
$PythonW = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $PythonW) {
    throw '找不到 pythonw.exe。请安装 Python 3.12+ 并勾选 “Add to PATH”，或先运行一次 DeepSeek Harness。'
}

# ---- 生成静默启动器 ----
$vbs = @"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "$AppDir"
sh.Run """$PythonW"" ""$App""", 0, False
"@
Set-Content -LiteralPath $RunVbs -Value $vbs -Encoding Default
Write-Host "已生成启动器：$RunVbs"

# ---- 开机自启用静默版（不弹设置窗）----
$RunSilentVbs = Join-Path $AppDir 'run-silent.vbs'
$vbsSilent = @"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "$AppDir"
sh.Run """$PythonW"" ""$App"" --silent", 0, False
"@
Set-Content -LiteralPath $RunSilentVbs -Value $vbsSilent -Encoding Default

# ---- 控制台兜底启动器（万一 wscript 被策略拦截）----
$bat = @"
@echo off
cd /d "%~dp0"
start "" "$PythonW" "%~dp0app.py"
"@
Set-Content -LiteralPath (Join-Path $AppDir 'start.bat') -Value $bat -Encoding Default
Write-Host "已生成兜底启动器：$(Join-Path $AppDir 'start.bat')"

# ---- 桌面快捷方式 ----
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($Link)
$shortcut.TargetPath = 'wscript.exe'
$shortcut.Arguments = """$RunVbs"""
$shortcut.WorkingDirectory = $AppDir
$shortcut.WindowStyle = 7
$shortcut.Description = 'Interpres：划词 AI 翻译'
        # 图标要放在工作区之外：Explorer 读不到沙箱工作区里的文件
        $IconSrc = Join-Path $AppDir 'assets\reading-companion.ico'
        $IconDir = Join-Path $env:LOCALAPPDATA 'reading-companion'
        if (Test-Path $IconSrc) {
            New-Item -ItemType Directory -Force -Path $IconDir | Out-Null
            $IconFile = Join-Path $IconDir 'rc.ico'
            Copy-Item $IconSrc $IconFile -Force
            $shortcut.IconLocation = "$IconFile,0"
        }
$shortcut.Save()
Write-Host "已创建桌面快捷方式：$Link"

# ---- 开机自启 ----
if ($Startup) {
    $auto = $shell.CreateShortcut($StartupLink)
    $auto.TargetPath = 'wscript.exe'
    $auto.Arguments = """$RunSilentVbs"""
    $auto.WorkingDirectory = $AppDir
    $auto.WindowStyle = 7
    if (Test-Path $IconFile) { $auto.IconLocation = "$IconFile,0" }
    $auto.Save()
    Write-Host "已设置开机自启（静默）：$StartupLink"
}

Write-Host ''
Write-Host '安装完成。'
Write-Host '  1) 双击桌面「Interpres」即可，会直接打开设置窗口，无黑窗口'
Write-Host '  2) 第一次用要先填 DeepSeek API Key，点「测试连接」通过后点「保存」'
Write-Host '  3) 在 PDF / EPUB 阅读器里选中文字，点「译」按钮；或按 Ctrl+Alt+T'
Write-Host '  4) 程序常驻后台，随时再双击图标可以回到设置'
Write-Host ''
Write-Host "Python: $PythonW"

