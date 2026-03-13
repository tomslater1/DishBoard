$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonCmd = $venvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} else {
    throw "Python was not found. Create .venv first or install Python on PATH."
}

$version = (& $pythonCmd -c "from utils.version import APP_VERSION; print(APP_VERSION)").Trim()
Write-Host "[build] Building DishBoard $version (Windows)"

if ($env:SKIP_PRECHECKS -ne '1') {
    Write-Host "[build] Running pre-release checks..."
    & $pythonCmd scripts/pre_release_checks.py
} else {
    Write-Host "[build] Skipping pre-release checks (SKIP_PRECHECKS=1)"
}

Write-Host "[build] Cleaning dist/ and build/..."
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path build) { Remove-Item build -Recurse -Force }

Write-Host "[build] Running PyInstaller..."
& $pythonCmd -m PyInstaller DishBoard.spec --clean -y

$distDir = Join-Path (Get-Location) 'dist\\DishBoard'
if (-not (Test-Path $distDir)) {
    throw "Expected build output not found: $distDir"
}

$zipName = "DishBoard-$version-windows.zip"
$zipPath = Join-Path (Get-Location) ("dist\\" + $zipName)
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "[build] Creating $zipName..."
Compress-Archive -Path "$distDir\\*" -DestinationPath $zipPath

Write-Host ""
Write-Host "[build] Windows build complete!"
Write-Host "   Folder: $distDir"
Write-Host "   Zip:    $zipPath"
