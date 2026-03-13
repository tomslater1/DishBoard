$ErrorActionPreference = 'Stop'

$version = python -c "from utils.version import APP_VERSION; print(APP_VERSION)"
Write-Host "▶ Building DishBoard $version (Windows)"

if ($env:SKIP_PRECHECKS -ne '1') {
    Write-Host "▶ Running pre-release checks..."
    python scripts/pre_release_checks.py
} else {
    Write-Host "⚠  Skipping pre-release checks (SKIP_PRECHECKS=1)"
}

Write-Host "▶ Cleaning dist/ and build/..."
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path build) { Remove-Item build -Recurse -Force }

Write-Host "▶ Running PyInstaller..."
pyinstaller DishBoard.spec --clean -y

$distDir = Join-Path (Get-Location) 'dist\\DishBoard'
if (-not (Test-Path $distDir)) {
    throw "Expected build output not found: $distDir"
}

$zipName = "DishBoard-$version-windows.zip"
$zipPath = Join-Path (Get-Location) ("dist\\" + $zipName)
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "▶ Creating $zipName..."
Compress-Archive -Path "$distDir\\*" -DestinationPath $zipPath

Write-Host ""
Write-Host "✅ Windows build complete!"
Write-Host "   Folder: $distDir"
Write-Host "   Zip:    $zipPath"
