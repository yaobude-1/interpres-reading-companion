param([string]$Path)
# 用 WPF MediaPlayer 播放 mp3（SoundPlayer 只支持 wav）
$ErrorActionPreference = "Stop"
try {
    Add-Type -AssemblyName PresentationCore
    $player = New-Object System.Windows.Media.MediaPlayer
    $player.Open([uri]$Path)
    $player.Play()
    $deadline = (Get-Date).AddSeconds(90)
    while ($true) {
        if ($player.NaturalDuration.HasTimeSpan) {
            if ($player.Position -ge $player.NaturalDuration.TimeSpan) { break }
        }
        if ((Get-Date) -gt $deadline) { break }
        Start-Sleep -Milliseconds 80
    }
    $player.Stop()
    $player.Close()
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
