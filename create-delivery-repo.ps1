# ==============================================
#  工商业储能优化配置系统 — 交付仓库生成脚本
#  用法：在 PowerShell 中运行此脚本
# ==============================================

$ErrorActionPreference = "Stop"

# ---- 配置 ----
$SourceDir    = "D:\storage_web_platform_3"
$DeliveryDir  = "D:\cess-delivery"

# ---- 安全检查 ----
if (-not (Test-Path $SourceDir)) {
    Write-Host "[ERROR] 源目录不存在: $SourceDir" -ForegroundColor Red
    exit 1
}
if (Test-Path $DeliveryDir) {
    Write-Host "[ERROR] 交付目录已存在: $DeliveryDir" -ForegroundColor Red
    Write-Host "  → 请手动删除该目录后重试，或修改脚本中 `$DeliveryDir` 路径"
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  工商业储能优化配置系统（交付版）" -ForegroundColor Cyan
Write-Host "  交付仓库生成器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "源目录  : $SourceDir"
Write-Host "交付目录: $DeliveryDir"
Write-Host ""

# ---- 1. 创建目录结构 ----
Write-Host "[1/5] 创建交付目录结构..." -ForegroundColor Yellow

New-Item -ItemType Directory -Force -Path "$DeliveryDir" | Out-Null
New-Item -ItemType Directory -Force -Path "$DeliveryDir\backend\routes" | Out-Null
New-Item -ItemType Directory -Force -Path "$DeliveryDir\backend\static\assets" | Out-Null
New-Item -ItemType Directory -Force -Path "$DeliveryDir\storage_engine_project" | Out-Null
New-Item -ItemType Directory -Force -Path "$DeliveryDir\OpenDSS" | Out-Null

# ---- 2. 复制文件 ----
Write-Host "[2/5] 复制交付文件..." -ForegroundColor Yellow

# 根目录文件
Copy-Item "$SourceDir\start.bat"                "$DeliveryDir\" -Force
Copy-Item "$SourceDir\pyproject.toml"            "$DeliveryDir\" -Force
Copy-Item "$SourceDir\README.md"                 "$DeliveryDir\" -Force
Copy-Item "$SourceDir\.env.example"              "$DeliveryDir\" -Force

# backend 核心
Copy-Item "$SourceDir\backend\storage_fastapi_backend.py" "$DeliveryDir\backend\" -Force
Copy-Item "$SourceDir\backend\routes\*"                  "$DeliveryDir\backend\routes\" -Force -Recurse
Copy-Item "$SourceDir\backend\models\*"                  "$DeliveryDir\backend\models\" -Force -Recurse
Copy-Item "$SourceDir\backend\services\*"                "$DeliveryDir\backend\services\" -Force -Recurse

# 前端预构建（backend/static）
Copy-Item "$SourceDir\backend\static\*" "$DeliveryDir\backend\static\" -Force -Recurse

# 求解器引擎（仅 .py 文件，排除 __pycache__、.idea、inputs）
Get-ChildItem "$SourceDir\storage_engine_project" -Recurse -Filter "*.py" | ForEach-Object {
    $relative = $_.FullName.Substring($SourceDir.Length + 1)
    $target   = Join-Path $DeliveryDir $relative
    $targetDir = Split-Path $target -Parent
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    }
    Copy-Item $_.FullName $target -Force
}

# OpenDSS 测试馈线模型
Copy-Item "$SourceDir\OpenDSS\*" "$DeliveryDir\OpenDSS\" -Force -Recurse

Write-Host "  → 文件复制完成" -ForegroundColor Green

# ---- 3. 生成交付专用的 .gitignore ----
Write-Host "[3/5] 生成 .gitignore..." -ForegroundColor Yellow

$gitignore = @"
# Python
.venv/
__pycache__/
*.py[cod]
*.egg-info/

# 运行时生成
data/
logs/
python/
.deps_installed

# 环境变量（含密钥）
.env

# IDE
.idea/
.vscode/
*.swp
*.swo

# 系统文件
.DS_Store
Thumbs.db
"@

Set-Content -Path "$DeliveryDir\.gitignore" -Value $gitignore -Encoding UTF8

# ---- 4. 删除不应包含的目录（安全清理） ----
Write-Host "[4/5] 清理排除项..." -ForegroundColor Yellow

# 删除求解器引擎中意外带入的非 .py 目录
$dirsToRemove = @(
    "$DeliveryDir\storage_engine_project\.idea",
    "$DeliveryDir\storage_engine_project\inputs",
    "$DeliveryDir\storage_engine_project\__pycache__"
)
foreach ($d in $dirsToRemove) {
    if (Test-Path $d) {
        Remove-Item $d -Recurse -Force
        Write-Host "  → 删除: $d"
    }
}
Write-Host "  → 清理完成" -ForegroundColor Green

# ---- 5. 初始化 Git ----
Write-Host "[5/5] 初始化 Git 仓库..." -ForegroundColor Yellow

Push-Location $DeliveryDir
git init
git add -A
git status
Pop-Location

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  交付仓库生成完毕！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "交付目录: $DeliveryDir"
Write-Host ""
Write-Host "接下来请手动执行以下命令（替换为你的仓库地址）："
Write-Host ""
Write-Host "  cd D:\cess-delivery"
Write-Host "  git commit -m 'init: 工商业储能优化配置系统（交付版）'"
Write-Host "  git remote add origin https://github.com/Minggshen/cess-energy-storage-delivery.git"
Write-Host "  git push -u origin main"
Write-Host ""
