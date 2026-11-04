param([string]$ReleaseRoot = "dist")

$ErrorActionPreference = "Stop"

$Python = "D:\ProgramData\Anaconda3\envs\quant312\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到 quant312 Python：$Python"
}
$PythonRoot = Split-Path $Python -Parent
$TclLibrary = Join-Path $PythonRoot "Library\lib\tcl8.6"
$TkLibrary = Join-Path $PythonRoot "Library\lib\tk8.6"
if ((Test-Path -LiteralPath $TclLibrary) -and (Test-Path -LiteralPath $TkLibrary)) {
    # Force PyInstaller to collect Tcl/Tk data matching this Python's linked Tcl runtime.
    $env:TCL_LIBRARY = $TclLibrary
    $env:TK_LIBRARY = $TkLibrary
}
& $Python -c "import PyInstaller, requests, PIL, cryptography; print('Build Python:', __import__('sys').executable); print('PyInstaller:', PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) { throw "quant312 缺少 PyInstaller/requests/Pillow，请先在 quant312 中安装打包依赖。" }

Push-Location $PSScriptRoot
try {
    $PyInstallerArgs = @("--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "料料统一小助手", "--collect-all", "PIL", "--collect-all", "requests")
    $FfiDll = Join-Path (Split-Path $Python -Parent) "Library\bin\ffi.dll"
    if (Test-Path -LiteralPath $FfiDll) { $PyInstallerArgs += @("--add-binary", "${FfiDll};.") }
    foreach ($DllName in @("tcl86t.dll", "tk86t.dll")) {
        $TclTkDll = Join-Path (Split-Path $Python -Parent) "Library\bin\$DllName"
        if (Test-Path -LiteralPath $TclTkDll) { $PyInstallerArgs += @("--add-binary", "${TclTkDll};.") }
    }
    $PyInstallerArgs += "run_publisher.py"
    $PyInstallerArgs += @("--distpath", (Join-Path $PSScriptRoot $ReleaseRoot),
        "--workpath", (Join-Path $PSScriptRoot "build_quant312"),
        "--specpath", (Join-Path $PSScriptRoot "build_quant312"))
    & $Python -m PyInstaller @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }
} finally {
    Pop-Location
}

$ReleaseDir = Join-Path $PSScriptRoot "$ReleaseRoot\料料统一小助手"
@'
运行说明

双击 料料统一小助手.exe 启动程序。首次使用时在平台登录页面分别登录壹料、料商宝、料小宝。
商家监控支持壹料、红料、料商宝和料小宝，请使用各自的用户监控登录页，再到商家监控勾选账号。
料商宝、料小宝的商家发布与用户监控独立登录，分别保存会话。
登录会话和文章标题映射会保存在本目录；请勿公开分享这些运行后生成的 JSON 文件。
默认价格、常用价格和标签可在统一发布页面的“默认设置”中保存。
请将整个 料料统一小助手 文件夹复制到目标电脑，不要只复制 EXE。
'@ | Set-Content -LiteralPath (Join-Path $ReleaseDir "运行说明.txt") -Encoding UTF8
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'RELEASE_NOTES.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'RELEASE_NOTES.md') -Destination $ReleaseDir
}

$ZipPath = Join-Path $PSScriptRoot "$ReleaseRoot\料料统一小助手-便携版.zip"
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "发布包已生成：$ZipPath"
