# Offline narration with the Windows built-in speech synthesizer (SAPI).
# Reads a JSON array of {"file": "<wav path>", "text": "<sentence>"} and writes one WAV per entry.
param(
    [Parameter(Mandatory = $true)][string]$Lines,
    [string]$Voice = "Microsoft Zira Desktop",
    [int]$Rate = 0
)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice($Voice)
$synth.Rate = $Rate
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($line in (Get-Content -Raw -Encoding UTF8 $Lines | ConvertFrom-Json)) {
    $synth.SetOutputToWaveFile($line.file, $format)
    $synth.Speak($line.text)
}
$synth.SetOutputToNull()
$synth.Dispose()
