# CampusOverflow 一键启动器（Windows PowerShell 5.1 兼容）
# 源码：scripts/launcher/campus_launcher.ps1；编译产物：仓库根 CampusOverflow-Launcher.exe
# 用法：双击 exe 进菜单；或  -Check 仅做环境自检
# 职责：docker compose 起 db/redis → alembic upgrade → 三个窗口分别起 API/worker/前端 → 开浏览器
# 端口：自动避开 Windows Hyper-V 动态保留区（台账教训：8000/8002/8080/8123 可能被收编）

[CmdletBinding()]
param([switch]$Check)

# 注意：docker/alembic 常把进度写到 stderr，PowerShell 在 Stop 模式下会当成异常抛出
# （实测 "Container xxx Running" 被误报为启动失败）——故用 Continue，失败一律以 $LASTEXITCODE 判定。
$ErrorActionPreference = 'Continue'

# ---------- 定位仓库根（exe 在根、脚本在 scripts/launcher 都能找到） ----------
function Find-Root {
    $dirs = @()
    if ($PSScriptRoot) { $dirs += $PSScriptRoot; $dirs += (Split-Path -Parent $PSScriptRoot); $dirs += (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) }
    $exeDir = Split-Path -Parent ([System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName)
    $dirs = @($exeDir) + $dirs
    foreach ($d in $dirs) {
        if ((Test-Path -LiteralPath (Join-Path $d 'docker-compose.yml')) -and (Test-Path -LiteralPath (Join-Path $d 'app\main.py'))) { return $d }
    }
    throw '找不到仓库根（需同时含 docker-compose.yml 与 app\main.py），请把 exe 放在仓库根目录运行。'
}

# ---------- Windows 保留端口探测 ----------
function Get-ExcludedPortRanges {
    $out = & netsh interface ipv4 show excludedportrange protocol=tcp 2>$null
    $ranges = @()
    foreach ($line in $out) {
        if ($line -match '^\s*(\d+)\s*-\s*(\d+)\s*$') { $ranges += ,@([int]$Matches[1], [int]$Matches[2]) }
    }
    return $ranges
}

function Test-PortUsable([int]$p, $excluded) {
    foreach ($r in $excluded) { if ($p -ge $r[0] -and $p -le $r[1]) { return $false } }
    if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { return $false }
    return $true
}

function Select-ApiPort {
    $excluded = Get-ExcludedPortRanges
    foreach ($p in @(8123, 8500, 8600, 8700, 9000, 9100, 9200, 5373)) {
        if (Test-PortUsable $p $excluded) { return $p }
    }
    throw '候选端口全部被占/被保留，请手动指定（编辑脚本 Select-ApiPort 候选表）。'
}

# ---------- pnpm 解析（PATH 损坏时兜底：npm prefix / 常见安装位逐个探测） ----------
function Get-Pnpm {
    $c = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $prefix = (& npm config get prefix 2>$null)
    if ($prefix) { $p = Join-Path ([string]$prefix.Trim()) 'pnpm.cmd'; if (Test-Path -LiteralPath $p) { return $p } }
    foreach ($cand in @("$env:APPDATA\npm\pnpm.cmd", "$env:LOCALAPPDATA\pnpm\pnpm.cmd")) {
        if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
    }
    return $null
}

# ---------- docker 解析（PATH 损坏时兜底：常见安装位探测） ----------
function Get-Docker {
    $c = Get-Command docker -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($cand in @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    )) {
        if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
    }
    return $null
}

# ---------- 环境自检 ----------
function Invoke-Check {
    $root = Find-Root
    Write-Host "== CampusOverflow 环境自检（根：$root）==" -ForegroundColor Cyan
    $ok = $true

    $dockerCmd = Get-Docker
    if (-not $dockerCmd) { Write-Host '[×] 找不到 docker CLI——请先安装并启动 Docker Desktop' -ForegroundColor Red; $ok = $false }
    else {
        & $dockerCmd info 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Host '[×] docker 守护进程未运行——请启动 Docker Desktop 后重试' -ForegroundColor Red; $ok = $false }
        else { Write-Host "[√] Docker 就绪（$dockerCmd）" -ForegroundColor Green }
    }

    if (Test-Path -LiteralPath (Join-Path $root '.venv\Scripts\python.exe')) { Write-Host '[√] 后端 venv 就绪' -ForegroundColor Green }
    else { Write-Host '[×] 缺 .venv——先执行: python -m venv .venv 且 .venv\Scripts\pip install -r requirements-dev.txt' -ForegroundColor Red; $ok = $false }

    $pnpm = Get-Pnpm
    if ($pnpm) { Write-Host "[√] pnpm 就绪（$pnpm）" -ForegroundColor Green }
    else { Write-Host '[×] 找不到 pnpm——npm install -g pnpm@10，或运行官方脚本 iwr https://get.pnpm.io/install.ps1 -useb | iex' -ForegroundColor Red; $ok = $false }

    if (Test-Path -LiteralPath (Join-Path $root 'frontend\node_modules')) { Write-Host '[√] 前端依赖已装' -ForegroundColor Green }
    else { Write-Host '[!] 前端依赖未装（启动时会自动 pnpm install，首次较慢）' -ForegroundColor Yellow }

    $apiPort = Select-ApiPort
    Write-Host "[√] API 端口可用：$apiPort（已避开 Windows 保留区）" -ForegroundColor Green
    if ($ok) { Write-Host '自检通过，可以启动。' -ForegroundColor Green } else { Write-Host '自检存在 × 项，先修复再启动。' -ForegroundColor Yellow }
    return $apiPort
}

# ---------- 启动 ----------
function New-ServiceWindow([string]$title, [string]$command) {
    Start-Process powershell -ArgumentList @('-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='$title'; $command") | Out-Null
}

function Start-All {
    $root = Find-Root
    $apiPort = Invoke-Check
    Write-Host "`n开始启动全栈……" -ForegroundColor Cyan

    $dockerCmd = Get-Docker
    if (-not $dockerCmd) { throw '找不到 docker CLI，无法启动容器' }
    Push-Location $root
    & $dockerCmd compose up -d 2>&1 | Out-Default
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'docker compose up 失败' }
    Write-Host '等待 db/redis 健康……' -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds(90)
    $dbH = ''; $rdH = ''
    while ((Get-Date) -lt $deadline) {
        $dbId = (& $dockerCmd compose ps -q db 2>$null); $rdId = (& $dockerCmd compose ps -q redis 2>$null)
        $dbH = (& $dockerCmd inspect -f '{{.State.Health.Status}}' $dbId 2>$null); $rdH = (& $dockerCmd inspect -f '{{.State.Health.Status}}' $rdId 2>$null)
        if ($dbH -eq 'healthy' -and $rdH -eq 'healthy') { break }
        Start-Sleep -Seconds 2
    }
    if ($dbH -ne 'healthy' -or $rdH -ne 'healthy') { Pop-Location; throw "db=$dbH redis=$rdH 未在 90s 内 healthy" }
    Write-Host '[√] db/redis healthy' -ForegroundColor Green

    & '.venv\Scripts\python.exe' -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'alembic upgrade 失败' }
    Write-Host '[√] 迁移到 head' -ForegroundColor Green

    New-ServiceWindow 'CO-API' "Set-Location -LiteralPath '$root'; & '.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port $apiPort"
    New-ServiceWindow 'CO-WORKER' "Set-Location -LiteralPath '$root'; & '.venv\Scripts\python.exe' -m celery -A app.contexts.reputation.infrastructure.celery_app worker --pool=solo -l info"
    $pnpmCmd = Get-Pnpm
    if (-not $pnpmCmd) { Pop-Location; throw '找不到 pnpm，无法启动前端' }
    $feInstall = "if (-not (Test-Path 'node_modules')) { & '$pnpmCmd' install }; & '$pnpmCmd' dev"
    New-ServiceWindow 'CO-FRONT' "`$env:VITE_API_TARGET='http://127.0.0.1:$apiPort'; Set-Location -LiteralPath '$root\frontend'; $feInstall"

    Write-Host "等待 API 就绪（http://127.0.0.1:$apiPort/health）……" -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds(90)
    $apiUp = $false
    while ((Get-Date) -lt $deadline) {
        try { if ((Invoke-WebRequest -Uri "http://127.0.0.1:$apiPort/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $apiUp = $true; break } } catch { }
        Start-Sleep -Seconds 2
    }
    if (-not $apiUp) { Pop-Location; throw 'API 90s 内未就绪，请查看 CO-API 窗口报错' }
    Write-Host '[√] API 就绪' -ForegroundColor Green

    $deadline = (Get-Date).AddSeconds(180)   # 前端首次含 pnpm install
    $feUp = $false
    while ((Get-Date) -lt $deadline) {
        try { Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 3 | Out-Null; $feUp = $true; break } catch { }
        Start-Sleep -Seconds 3
    }
    if ($feUp) { Write-Host '[√] 前端就绪' -ForegroundColor Green } else { Write-Host '[!] 前端 180s 未就绪，看 CO-FRONT 窗口（首次装依赖可能超时，属正常，稍后手动开 http://localhost:5173）' -ForegroundColor Yellow }

    Pop-Location
    Write-Host "`n全栈已起：前端 http://localhost:5173 ｜ API http://127.0.0.1:$apiPort/docs ｜ 声誉 worker 见 CO-WORKER 窗口" -ForegroundColor Green
    Start-Process 'http://localhost:5173'
}

# ---------- 停止 ----------
function Stop-All {
    $root = Find-Root
    Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'CO-*' } | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    $dockerCmd = Get-Docker
    if (-not $dockerCmd) { Write-Host '找不到 docker CLI，跳过容器停止' -ForegroundColor Red; return }
    Push-Location $root
    & $dockerCmd compose stop 2>&1 | Out-Default
    Pop-Location
    Write-Host '已停止（数据保留在命名卷 pgdata）。' -ForegroundColor Green
}

# ---------- 状态 ----------
function Show-Status {
    $root = Find-Root
    $dockerCmd = Get-Docker
    if (-not $dockerCmd) { Write-Host '找不到 docker CLI' -ForegroundColor Red; return }
    Push-Location $root
    & $dockerCmd compose ps 2>&1 | Out-Default
    Pop-Location
    try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8123/health' -UseBasicParsing -TimeoutSec 3; Write-Host "API(8123): $($r.StatusCode)" } catch { Write-Host 'API(8123): 未响应（端口以启动时打印为准）' }
}

# ---------- 入口 ----------
if ($Check) { Invoke-Check | Out-Null; exit 0 }

Write-Host 'CampusOverflow 启动器' -ForegroundColor Cyan
Write-Host '  [1] 启动全栈   [2] 停止   [3] 状态   [4] 环境自检   [0] 退出'
while ($true) {
    $choice = Read-Host '选择'
    switch ($choice) {
        '1' { try { Start-All } catch { Write-Host "启动失败：$_" -ForegroundColor Red } }
        '2' { Stop-All }
        '3' { Show-Status }
        '4' { Invoke-Check | Out-Null }
        '0' { exit 0 }
        default { Write-Host '无效选项' }
    }
}
