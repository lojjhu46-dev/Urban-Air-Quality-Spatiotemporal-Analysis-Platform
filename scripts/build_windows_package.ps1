param(
    [string]$Name = "AQDashboard"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DistRoot = Join-Path $Root "dist"
$PackageDir = Join-Path $DistRoot $Name
$AppDir = Join-Path $PackageDir "app"

if (-not (Test-Path $Python)) {
    throw "Cannot find virtualenv Python at $Python"
}

Push-Location $Root
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --name $Name `
        --collect-all streamlit `
        --collect-all pandas `
        --collect-all pyarrow `
        --collect-all plotly `
        --collect-all scipy `
        --collect-all numpy `
        --collect-all pydeck `
        --distpath $DistRoot `
        --workpath (Join-Path $Root "build\pyinstaller") `
        --specpath (Join-Path $Root "build") `
        "scripts\launch_dashboard.py"

    if (Test-Path $AppDir) {
        Remove-Item $AppDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "scripts") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $AppDir ".streamlit") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "data\raw") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "data\processed") | Out-Null

    Copy-Item "app.py" $AppDir
    Copy-Item "pages" $AppDir -Recurse
    Copy-Item "src" $AppDir -Recurse
    Copy-Item "scripts\generate_demo_data.py" (Join-Path $AppDir "scripts\generate_demo_data.py") -Force
    Copy-Item "scripts\build_dataset.py" (Join-Path $AppDir "scripts\build_dataset.py") -Force
    Copy-Item "requirements.txt" $AppDir
    Copy-Item ".streamlit\config.toml" (Join-Path $AppDir ".streamlit\config.toml") -Force
    Copy-Item ".streamlit\secrets.toml.example" (Join-Path $AppDir ".streamlit\secrets.toml.example") -Force

    if (Test-Path "data\processed\beijing_aq.parquet") {
        Copy-Item "data\processed\beijing_aq.parquet" (Join-Path $AppDir "data\processed\beijing_aq.parquet") -Force
    }
    if (Test-Path "data\processed\beijing_aq.csv") {
        Copy-Item "data\processed\beijing_aq.csv" (Join-Path $AppDir "data\processed\beijing_aq.csv") -Force
    }
    if (Test-Path "data\processed\agent_runs") {
        Copy-Item "data\processed\agent_runs" (Join-Path $AppDir "data\processed\agent_runs") -Recurse -Force
    }

    @"
城市空气质量时空分析与历史采集系统

运行方式：
1. 双击 $Name.exe。
2. 程序会自动选择本地端口并打开浏览器。
3. 使用期间请保持启动窗口打开。
4. 关闭窗口或按 Ctrl+C 可停止程序。

配置 DeepSeek：
1. 复制 app\.streamlit\secrets.toml.example 为 app\.streamlit\secrets.toml。
2. 填入 deepseek_api_key 后重新启动 $Name.exe。

数据目录：
- 默认数据集：app\data\processed\beijing_aq.parquet
- Agent 采集结果：app\data\processed\agent_runs\
"@ | Set-Content -Encoding UTF8 (Join-Path $PackageDir "README_运行说明.txt")

    Write-Host "Package created: $PackageDir"
}
finally {
    Pop-Location
}
