param(
    [Parameter(Mandatory = $true)][string]$HwndFile
)

# UIA 契约测试的“被读窗口”：WPF RichTextBox 在 UI Automation 里是
# ControlType=Document，带 TextPattern 和真实选区，正好匹配
# rc/uia_context.ps1 的候选筛选条件。启动后把 HWND 写进 $HwndFile。
# 调用方负责结束进程（测试在 finally 里 kill）。

$ErrorActionPreference = 'Stop'

function Write-Status([string]$text) {
    [IO.File]::WriteAllText($HwndFile, $text)
}

try {
    Add-Type -AssemblyName PresentationFramework
    Add-Type -AssemblyName PresentationCore
    Add-Type -AssemblyName WindowsBase
} catch {
    Write-Status ('SKIP: ' + $_.Exception.Message)
    exit 0
}

try {
    $window = New-Object System.Windows.Window
    $window.Title = 'Interpres UIA Contract Target'
    $window.Width = 520
    $window.Height = 240

    $rtb = New-Object System.Windows.Controls.RichTextBox
    $doc = New-Object System.Windows.Documents.FlowDocument
    $para = New-Object System.Windows.Documents.Paragraph
    $run = New-Object System.Windows.Documents.Run(
        'The quick brown fox jumps over the lazy dog. A second sentence keeps the paragraph long enough to be useful.')
    $para.Inlines.Add($run)
    $doc.Blocks.Add($para)
    $rtb.Document = $doc
    $window.Content = $rtb

    $window.Show()
    $rtb.SelectAll()
    $rtb.Focus() | Out-Null

    $interop = New-Object System.Windows.Interop.WindowInteropHelper($window)
    Write-Status ([string]$interop.Handle)

    $app = New-Object System.Windows.Application
    $app.Run($window) | Out-Null
    exit 0
} catch {
    Write-Status ('ERROR: ' + $_.Exception.Message)
    exit 1
}
