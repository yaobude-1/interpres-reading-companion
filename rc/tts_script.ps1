param([string]$InFile,[string]$OutFile,[string]$Voice)
$ErrorActionPreference = 'Stop'
$synth = $null
try {
    Add-Type -AssemblyName System.Speech
    $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $InFile
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'empty text' }
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    if ($Voice -ne '') {
        try { $synth.SelectVoice($Voice) } catch { }
    }
    $synth.SetOutputToWaveFile($OutFile)
    $synth.Speak($text)
    $name = $synth.Voice.Name
    $synth.Dispose()
    $synth = $null
    Write-Output $name
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    if ($synth -ne $null) { try { $synth.Dispose() } catch { } }
    if (Test-Path -LiteralPath $OutFile) { Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue }
    exit 1
}
