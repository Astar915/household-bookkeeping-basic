$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildEnvironment = Join-Path ([System.IO.Path]::GetTempPath()) "household-bookkeeping-pyinstaller"
$BuildPython = Join-Path $BuildEnvironment "Scripts\python.exe"
$DistPath = Join-Path $Root "dist"
$ExecutablePath = Join-Path $DistPath "HouseholdBookkeeping-Windows-x64.exe"
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
    "--onefile"
    "--windowed"
    "--name"
    "HouseholdBookkeeping-Windows-x64"
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

if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    throw "PyInstaller completed but the executable was not found: $ExecutablePath"
}

Write-Host "Windows app: $ExecutablePath"
