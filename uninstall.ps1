# Uninstall Interpres: stop it, remove shortcuts and (optionally) user data.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
#   powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -KeepData
#   powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -DryRun
#
# The app itself is portable: this script only removes the known locations it
# created. It never touches the registry and never searches for unrelated files.

param(
    [string]$AppDir = $PSScriptRoot,
    [switch]$KeepData,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Say([string]$text) { Write-Host $text }
function Remove-IfExists([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    if ($DryRun) { Say "  [dry-run] would remove $path"; return }
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    Say "  removed $path"
}

if (-not $AppDir) { $AppDir = $PSScriptRoot }
$resolved = Resolve-Path -LiteralPath $AppDir -ErrorAction SilentlyContinue
if (-not $resolved) { throw "找不到目录：$AppDir" }
$AppDir = $resolved.Path

# ---- safety checks ---------------------------------------------------------
if ($AppDir -eq [IO.Path]::GetPathRoot($AppDir)) {
    throw "拒绝在磁盘根目录运行：$AppDir"
}
if ($AppDir -eq $env:USERPROFILE) {
    throw "拒绝在用户主目录运行：$AppDir"
}
$hasExe = Test-Path -LiteralPath (Join-Path $AppDir 'Interpres.exe')
$hasSource = Test-Path -LiteralPath (Join-Path $AppDir 'app.py')
if (-not ($hasExe -or $hasSource)) {
    throw "这个目录看起来不是 Interpres：$AppDir（找不到 Interpres.exe 或 app.py）"
}
$isSourceCheckout = Test-Path -LiteralPath (Join-Path $AppDir '.git')

Say "Interpres 卸载：$AppDir"
if ($DryRun) { Say '（dry-run：只打印，不改动任何文件）' }

# ---- 1. stop running instances --------------------------------------------
Say ''
Say '1) 停止正在运行的 Interpres'
$stopped = 0
foreach ($proc in Get-CimInstance Win32_Process -ErrorAction SilentlyContinue) {
    $name = ([string]$proc.Name).ToLower()
    $cmd = [string]$proc.CommandLine
    $exePath = [string]$proc.ExecutablePath
    $matchesExe = $name -eq 'interpres.exe' -and $exePath -like "$AppDir*"
    $matchesSource = $name -eq 'pythonw.exe' -and $cmd -like "*$AppDir*" -and $cmd -like '*app.py*'
    if (-not ($matchesExe -or $matchesSource)) { continue }
    if ($DryRun) {
        Say "  [dry-run] would stop $($proc.Name) (pid $($proc.ProcessId))"
    } else {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        Say "  stopped $($proc.Name) (pid $($proc.ProcessId))"
    }
    $stopped++
}
if ($stopped -eq 0) { Say '  没有发现正在运行的实例' }

# ---- 2. shortcuts and the copied icon -------------------------------------
Say ''
Say '2) 删除快捷方式'
$shell = New-Object -ComObject WScript.Shell
$shortcuts = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Interpres.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Startup')) 'Interpres.lnk')
)
$removedShortcut = $false
foreach ($link in $shortcuts) {
    if (-not (Test-Path -LiteralPath $link)) { continue }
    $target = ''
    $args = ''
    try {
        $sc = $shell.CreateShortcut($link)
        $target = $sc.TargetPath
        $args = $sc.Arguments
    } catch {
        # 打不开就按名字删：这是本程序固定使用的快捷方式名
    }
    $ours = (-not $target) -or ($args -like "*$AppDir*") -or ($target -like "$AppDir*")
    if (-not $ours) {
        Say "  skipped $link（指向别处：$target）"
        continue
    }
    Remove-IfExists $link
    $removedShortcut = $true
}

$iconDir = Join-Path $env:LOCALAPPDATA 'reading-companion'
$iconFile = Join-Path $iconDir 'rc.ico'
if ($removedShortcut) {
    if (Test-Path -LiteralPath $iconFile) { Remove-IfExists $iconFile }
    if ((Test-Path -LiteralPath $iconDir) -and -not (Get-ChildItem -LiteralPath $iconDir -Force)) {
        Remove-IfExists $iconDir
    }
} else {
    Say '  没有找到属于这个目录的快捷方式，保留图标副本'
}

# ---- 3. user data ----------------------------------------------------------
Say ''
Say '3) 用户数据'
$dataDir = Join-Path $env:USERPROFILE '.reading-companion'
$deleteData = $false
if ($KeepData) {
    Say "  保留数据目录：$dataDir"
} elseif (Test-Path -LiteralPath $dataDir) {
    Say "  数据目录：$dataDir"
    Say '  里面有生词本、翻译记录、设置和 API Key（DPAPI 加密）。'
    if ($DryRun) {
        Say '  [dry-run] 正式运行时会询问是否删除这些数据'
    } else {
        $answer = Read-Host '  是否同时删除这些数据？输入 y 删除，直接回车保留 [y/N]'
        $deleteData = ($answer -eq 'y' -or $answer -eq 'Y')
        if ($deleteData) {
            Remove-IfExists $dataDir
        } else {
            Say '  已保留数据，下次安装/解压后会继续使用。'
        }
    }
} else {
    Say '  没有找到数据目录，跳过。'
}

# ---- 4. program folder -----------------------------------------------------
Say ''
Say '4) 删除程序目录'
if ($isSourceCheckout) {
    Say '  这是源码仓库（含 .git），不自动删除；请自行删除或在 git 里处理。'
    Say "  目录：$AppDir"
} elseif ($DryRun) {
    Say "  [dry-run] would remove $AppDir"
} else {
    $scriptInside = $PSCommandPath -like "$AppDir*"
    if ($scriptInside) {
        # Windows 会锁住正在运行的目录，交给一个延迟执行的 cmd 删除
        $inner = "ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$AppDir`""
        Start-Process -FilePath $env:ComSpec -ArgumentList '/c', $inner -WindowStyle Hidden
        Say '  已在后台安排删除（约 2 秒后）；如果目录还在，手动删除即可。'
    } else {
        Remove-Item -LiteralPath $AppDir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $AppDir) {
            Say "  删除失败（可能有进程还在占用），请手动删除：$AppDir"
        } else {
            Say "  已删除 $AppDir"
        }
    }
}

Say ''
Write-Host '卸载完成。' -ForegroundColor Green
if ($deleteData) { Write-Host '用户数据已删除。' }
