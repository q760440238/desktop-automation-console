# 构建 Flutter 桌面应用
#
# 为什么需要这个脚本：Flutter 的 Windows 构建链（CMake + MSBuild）在**中文路径**下会用
# GBK 读取 UTF-8 生成的工程文件，把路径解码成乱码导致编译失败。脚本建一个 ASCII 目录联接
# （junction）绕过去：源码保持原位，构建从 C:\dac_build 发起。
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build_flutter.ps1

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$Project  = Join-Path $Root 'flutter_app'
$BuildDir = Join-Path $env:SystemDrive 'dac_build'

$FlutterCmd = Get-Command flutter -ErrorAction SilentlyContinue
if ($null -eq $FlutterCmd) {
    throw '找不到 flutter 命令，请把 Flutter SDK 的 bin 目录加入 PATH'
}
$Flutter = $FlutterCmd.Source

if (-not (Test-Path (Join-Path $Project 'pubspec.yaml'))) { throw "找不到 Flutter 工程：$Project" }

# 1. 准备 ASCII 构建路径
if (Test-Path $BuildDir) {
    $item = Get-Item $BuildDir -Force
    if ($item.LinkType -ne 'Junction') { throw "$BuildDir 已存在且不是目录联接，请手动处理" }
} else {
    cmd /c mklink /J "$BuildDir" "$Project" | Out-Null
    Write-Host "已创建目录联接：$BuildDir -> $Project"
}

# 2. 构建
$env:HTTP_PROXY = ''
$env:HTTPS_PROXY = ''
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'

Push-Location $BuildDir
try {
    & $Flutter --no-version-check build windows --release
    if ($LASTEXITCODE -ne 0) { throw "构建失败（exit $LASTEXITCODE）" }
} finally {
    Pop-Location
}

$Exe = Join-Path $Project 'build\windows\x64\runner\Release\desktop_console.exe'
if (Test-Path $Exe) {
    Write-Host "构建成功：$Exe"
} else {
    throw '构建结束但没有找到产物'
}
