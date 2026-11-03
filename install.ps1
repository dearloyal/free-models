# 一键拉取并运行「每日免费模型」导入器 (Windows PowerShell)
# 用法:
#   irm https://raw.githubusercontent.com/dearloyal/free-models/main/install.ps1 | iex
#   # 想导到 DSH:  & { irm .../install.ps1 | iex } --dsh  (或直接跑 python oneclick.py --dsh)
$ErrorActionPreference = "Stop"
$repo = "https://github.com/dearloyal/free-models.git"
$dir  = if ($env:FREE_MODELS_DIR) { $env:FREE_MODELS_DIR } else { Join-Path $HOME "free-models" }

if (Test-Path (Join-Path $dir ".git")) {
  Write-Host "→ 更新已有仓库: $dir"
  git -C $dir pull --ff-only
} else {
  Write-Host "→ 克隆到: $dir"
  git clone --depth 1 $repo $dir
}

Set-Location $dir
$py = $null
foreach ($c in @("python", "py", "python3")) {
  if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break }
}
if (-not $py) {
  Write-Host "✗ 未找到 Python，请先安装 Python 3 (https://www.python.org/downloads/)" -ForegroundColor Red
  exit 1
}
Write-Host "→ 运行一键导入"
& $py oneclick.py @args
