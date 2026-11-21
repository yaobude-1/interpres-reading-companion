param(
    [Parameter(Mandatory = $true)][int]$Hwnd
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$result = [ordered]@{
    ok        = $false
    reason    = ''
    app       = ''
    selection = ''
    paragraph = ''
}

try {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
    try { $result.app = [string]$root.Current.Name } catch { }

    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::IsTextPatternAvailableProperty, $true)
    $candidates = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants, $condition)

    $pattern = $null
    foreach ($element in $candidates) {
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

    if ($null -eq $pattern) {
        $result.reason = 'no-text-pattern'
    } else {
        $ranges = @($pattern.GetSelection())
        if ($ranges.Count -eq 0) {
            $result.reason = 'no-selection'
        } else {
            $range = $ranges[0]
            $result.selection = ([string]$range.GetText(-1)).Trim()
            $paragraph = $range.Clone()
            $paragraph.ExpandToEnclosingUnit(
                [System.Windows.Automation.Text.TextUnit]::Paragraph)
            $result.paragraph = ([string]$paragraph.GetText(-1)).Trim()
            if ($result.selection.Length -eq 0) {
                $result.reason = 'empty-selection'
            } elseif ($result.paragraph.Length -eq 0) {
                $result.reason = 'empty-paragraph'
            } else {
                $result.ok = $true
            }
        }
    }
} catch {
    $result.reason = 'error: ' + $_.Exception.Message
}

$result | ConvertTo-Json -Compress
