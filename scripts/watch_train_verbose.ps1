$out = 'E:\aitest\pc-agent\data\train_final.out.log'
$err = 'E:\aitest\pc-agent\data\train_final.err.log'
$total = 3196
$ESC = [char]27
while ($true) {
    Clear-Host
    Write-Host "==================================================================" -ForegroundColor DarkCyan
    Write-Host "  PC-AGENT  -  Windows control AI  -  Dispatcher fine-tune" -ForegroundColor Cyan
    Write-Host "==================================================================" -ForegroundColor DarkCyan
    Write-Host "  base model : Gemma 4 E2B (abliterated)   QLoRA / NF4 4-bit" -ForegroundColor Gray
    Write-Host "  adapter    : LoRA r=16 a=32  attn+mlp proj   warm-start dispatcher-cur" -ForegroundColor Gray
    Write-Host "  dataset    : 25,827 ex  (function-calling + synth Windows actions)" -ForegroundColor Gray
    Write-Host "  schedule   : 2 epochs  seq 512  bsz1 x accum16  cosine lr 2e-4" -ForegroundColor Gray
    Write-Host "  hardware   : RTX 3080 Ti 12GB  (250W cap, fan 100%)" -ForegroundColor Gray
    $alive = Get-Process -Id 3284 -ErrorAction SilentlyContinue
    if ($alive) { Write-Host "  status     : RUNNING  (pid 3284)" -ForegroundColor Green }
    else        { Write-Host "  status     : FINISHED / STOPPED" -ForegroundColor Yellow }
    Write-Host "------------------------------------------------------------------" -ForegroundColor DarkCyan

    Write-Host "  metrics (logging_steps=10):" -ForegroundColor Cyan
    $metrics = ((Get-Content $out -Raw -ErrorAction SilentlyContinue) -split "`r|`n" |
                Where-Object { $_ -match "'loss'" } | Select-Object -Last 14)
    foreach ($m in $metrics) {
        $loss = if ($m -match "'loss': '([\d.]+)'") { $matches[1] } else { '?' }
        $acc  = if ($m -match "'mean_token_accuracy': '([\d.]+)'") { $matches[1] } else { '?' }
        $lr   = if ($m -match "'learning_rate': '([\d.eE+-]+)'") { $matches[1] } else { '?' }
        $ep   = if ($m -match "'epoch': '([\d.]+)'") { $matches[1] } else { '?' }
        Write-Host ("    loss {0,-7}  acc {1,-7}  lr {2,-11}  epoch {3}" -f $loss,$acc,$lr,$ep) -ForegroundColor Green
    }
    Write-Host "------------------------------------------------------------------" -ForegroundColor DarkCyan

    $line = ((Get-Content $err -Raw -ErrorAction SilentlyContinue) -split "`r|`n" |
             Where-Object { $_ -match "/$total \[" } | Select-Object -Last 1)
    if ($line) {
        Write-Host "  progress:" -ForegroundColor Cyan
        Write-Host "    $line" -ForegroundColor White
        if ($line -match '(\d+)/') {
            $step = [int]$matches[1]
            $pct  = [math]::Round(100.0 * $step / $total, 1)
            $barw = 50
            $fill = [int]($barw * $step / $total)
            $bar  = ('#' * $fill) + ('-' * ($barw - $fill))
            Write-Host ("    [$bar] $pct%  ($step/$total)") -ForegroundColor Yellow
        }
    } else { Write-Host "  progress: loading model weights..." -ForegroundColor Yellow }
    Write-Host "------------------------------------------------------------------" -ForegroundColor DarkCyan

    $g = nvidia-smi --query-gpu=memory.used,memory.total,power.draw,power.limit,temperature.gpu,fan.speed --format=csv,noheader
    Write-Host "  GPU: $g" -ForegroundColor White
    Write-Host "  (refreshes every 4s   |   Ctrl+C to close - does not affect training)" -ForegroundColor DarkGray
    Start-Sleep -Seconds 4
}
