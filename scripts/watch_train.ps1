$err = 'E:\aitest\pc-agent\data\train_final.err.log'
$total = 3196
while ($true) {
    Clear-Host
    Write-Host '=== PC-Agent Dispatcher Training (E2B QLoRA, 2 epochs) ===' -ForegroundColor Cyan
    Write-Host ''
    $alive = Get-Process -Id 3284 -ErrorAction SilentlyContinue
    if ($alive) { Write-Host 'STATUS: RUNNING  (PID 3284)' -ForegroundColor Green }
    else        { Write-Host 'STATUS: STOPPED / FINISHED' -ForegroundColor Yellow }
    Write-Host ''
    $line = ((Get-Content $err -Raw -ErrorAction SilentlyContinue) -split "`r|`n" |
             Where-Object { $_ -match "/$total \[" } | Select-Object -Last 1)
    if ($line) {
        Write-Host 'PROGRESS:' -ForegroundColor Cyan
        Write-Host "  $line" -ForegroundColor Green
        if ($line -match '(\d+)/' ) {
            $step = [int]$matches[1]
            $pct  = [math]::Round(100.0 * $step / $total, 1)
            Write-Host ("  step $step / $total   ($pct%)") -ForegroundColor White
        }
    } else { Write-Host 'PROGRESS: (loading model weights...)' -ForegroundColor Yellow }
    Write-Host ''
    $g = nvidia-smi --query-gpu=memory.used,power.draw,temperature.gpu,fan.speed --format=csv,noheader
    Write-Host "GPU: $g" -ForegroundColor White
    Write-Host ''
    Write-Host '(updates every 5s - leave open, Ctrl+C to close)' -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
}
