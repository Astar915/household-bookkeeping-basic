$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildEnvironment = Join-Path ([System.IO.Path]::GetTempPath()) "household-bookkeeping-pyinstaller"
$BuildPython = Join-Path $BuildEnvironment "Scripts\python.exe"
$DistPath = Join-Path $Root "dist"
$AppDirectory = Join-Path $DistPath "HouseholdBookkeeping"
$ArchivePath = Join-Path $DistPath "HouseholdBookkeeping-Windows-x64.zip"
$WorkPath = Join-Path ([System.IO.Path]::GetTempPath()) "household-bookkeeping-pyinstaller-work"
$SpecPath = Join-Path ([System.IO.Path]::GetTempPath()) "household-bookkeeping-pyinstaller-spec"

# The user's Windows profile may contain characters that the active console
# code page cannot print. Keep pip/PyInstaller diagnostics UTF-8 safe.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path -LiteralPath $BuildPython)) {
    $PythonCommand = Get-Command python -ErrorAction Stop
    & $PythonCommand.Source -m venv $BuildEnvironment
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the temporary Python build environment."
    }
}

& $BuildPython -m pip install --disable-pip-version-check --no-color --progress-bar off --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip in the temporary build environment." }
& $BuildPython -m pip install --disable-pip-version-check --no-color --progress-bar off -r (Join-Path $Root "requirements.txt") "pyinstaller>=6.17"
if ($LASTEXITCODE -ne 0) { throw "Could not install the desktop build dependencies." }

$BundledSkill = Join-Path $Root ".agents\skills\household-bookkeeping-software-v0-2\SKILL.md"
if (-not (Test-Path -LiteralPath $BundledSkill)) {
    throw "The public bookkeeping Skill is missing: $BundledSkill"
}

$Arguments = @(
    "--noconfirm"
    "--clean"
    "--onedir"
    "--windowed"
    "--name"
    "HouseholdBookkeeping"
    "--icon"
    (Join-Path $Root "assets\desktop-mark.ico")
    "--add-data"
    "$(Join-Path $Root 'assets');assets"
    "--add-data"
    "$BundledSkill;.agents/skills/household-bookkeeping-software-v0-2"
    "--collect-all"
    "tkinterdnd2"
    "--collect-all"
    "PIL"
    "--distpath"
    $DistPath
    "--workpath"
    $WorkPath
    "--specpath"
    $SpecPath
    (Join-Path $Root "bookkeeping\frozen_entry.py")
)

Push-Location $Root
try {
    & $BuildPython -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}

$ExecutablePath = Join-Path $AppDirectory "HouseholdBookkeeping.exe"
if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    throw "PyInstaller completed but the executable was not found: $ExecutablePath"
}

Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination $AppDirectory -Force
$QuickStart = @'
家庭记账 · Windows 免安装版

1. 保持本文件、HouseholdBookkeeping.exe 和 _internal 文件夹在一起。
2. 双击 HouseholdBookkeeping.exe 启动。
3. 首次启动会创建空账本；账本和个人设置保存在当前 Windows 用户的 AppData 中。
4. 自然语言记账需要自行配置模型服务；没有模型也能浏览和管理账本。

软件不会连接银行或代为付款。请在“设置 → 账本与备份”创建备份。
'@
[System.IO.File]::WriteAllText(
    (Join-Path $AppDirectory "快速开始.txt"),
    $QuickStart,
    [System.Text.UTF8Encoding]::new($false)
)

Compress-Archive -Path (Join-Path $AppDirectory "*") -DestinationPath $ArchivePath -Force
if (-not (Test-Path -LiteralPath $ArchivePath)) {
    throw "The Windows distribution archive was not created."
}

Write-Host "Windows app: $ExecutablePath"
Write-Host "Download archive: $ArchivePath"
