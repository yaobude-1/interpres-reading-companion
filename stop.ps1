"""停止所有「Interpres」实例。

只结束命令行里带 reading-companion 的 pythonw 进程，不会碰其他 Python 程序。
"""

$ErrorActionPreference = 'SilentlyContinue'

$targets = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*reading-companion*' }

if (-not $targets) {
    Write-Host '没有找到正在运行的「Interpres」。'
} else {
    foreach ($p in $targets) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "已停止 $($targets.Count) 个实例。"
}

Start-Sleep -Milliseconds 500
$still = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*reading-companion*' }
if ($still) {
    Write-Host '还有进程没退出，可以再用任务管理器结束 pythonw.exe。'
} else {
    Write-Host '现在可以重新双击桌面的「Interpres」了。'
}
