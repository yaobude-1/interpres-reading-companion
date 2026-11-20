param([string]$TextFile, [string]$OutFile, [string]$Lang = "en", [string]$Voice = "")
# OneCore 语音回退：走 Windows.Media.SpeechSynthesis（讲述人同款引擎）。
# 某些机器上桌面 SAPI 不可用（0x8004503A），但 OneCore 引擎是好的。
$ErrorActionPreference = "Stop"
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]

    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    if ($null -eq $asTask) { throw "no AsTask helper" }

    function Await($op, $type) {
        $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
        $task.Wait(-1) | Out-Null
        $task.Result
    }

    $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $TextFile
    if ([string]::IsNullOrWhiteSpace($text)) { throw "empty text" }

    $synth = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::new()
    $voices = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
    $pick = $null
    if ($Voice -ne "") {
        $pick = $voices | Where-Object { $_.DisplayName -eq $Voice } | Select-Object -First 1
    }
    if ($null -eq $pick) {
        $pick = $voices | Where-Object { $_.Language -like ($Lang + '*') } | Select-Object -First 1
    }
    if ($null -eq $pick) {
        $pick = $voices | Select-Object -First 1
    }
    if ($null -eq $pick) { throw "no installed voice" }
    $synth.Voice = $pick

    $stream = Await ($synth.SynthesizeTextToStreamAsync($text.Trim())) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = [Windows.Storage.Streams.DataReader]::new($stream.GetInputStreamAt(0))
    $size = [uint32]$stream.Size
    $null = Await ($reader.LoadAsync($size)) ([uint32])
    $bytes = New-Object byte[] $size
    $reader.ReadBytes($bytes)
    [System.IO.File]::WriteAllBytes($OutFile, $bytes)
    Write-Output ("onecore:" + $pick.DisplayName)
} catch {
    [Console]::Error.WriteLine("onecore 失败: " + $_.Exception.Message)
    if (Test-Path -LiteralPath $OutFile) {
        Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
    }
    exit 1
}
