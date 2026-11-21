param(
    [Parameter(Mandatory = $true)][int]$Hwnd
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Live2 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
}
"@

$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
$condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::IsTextPatternAvailableProperty, $true)

$pattern = $null
for ($attempt = 0; $attempt -lt 10 -and $null -eq $pattern; $attempt++) {
    foreach ($element in $root.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants, $condition)) {
        $isDocument = $element.Current.ControlType -eq [System.Windows.Automation.ControlType]::Document
        $looksRendered = $element.Current.ClassName -like '*RenderWidget*'
        if ($isDocument -or $looksRendered) {
            $candidate = $null
            if ($element.TryGetCurrentPattern(
                    [System.Windows.Automation.TextPattern]::Pattern, [ref]$candidate)) {
                $pattern = $candidate
                break
            }
        }
    }
    if ($null -eq $pattern) { Start-Sleep -Milliseconds 400 }
}
if ($null -eq $pattern) { throw 'no TextPattern in this window' }

[Live2]::SetWindowPos($Hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x0003) | Out-Null
[Live2]::SetForegroundWindow($Hwnd) | Out-Null
Start-Sleep -Milliseconds 500

$wsh = New-Object -ComObject WScript.Shell
$wsh.SendKeys('^a')
Start-Sleep -Milliseconds 700

$selected = @($pattern.GetSelection())
if ($selected.Count -eq 0) { throw 'Ctrl+A did not create a UIA selection' }
Write-Output ("selected: " + $selected[0].GetText(-1))
