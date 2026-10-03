# Сборка FreelanceDesk для Windows. Результат в папке dist:
#   FreelanceDesk\FreelanceDesk.exe       — программа (папкой)
#   FreelanceDesk-<версия>-portable.zip   — архив «распаковал и запустил»
#   FreelanceDesk-<версия>-Setup.exe      — установщик (если есть Inno Setup)
#
# Запуск из папки проекта:  .\build.ps1
# (если PowerShell запрещает скрипты: powershell -ExecutionPolicy Bypass -File build.ps1)

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }  # на GitHub Actions

# Версия — из пакета, чтобы не дублировать её вручную
$version = & $python -c "import sys; sys.path.insert(0, 'src'); import freelancedesk; print(freelancedesk.__version__)"
Write-Host "Сборка FreelanceDesk $version"

& $python -m pip install --quiet "pyinstaller>=6.10"
& $python -m PyInstaller freelancedesk.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }

# Переносная версия — архивом
$zip = "dist\FreelanceDesk-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\FreelanceDesk" -DestinationPath $zip
Write-Host "Архив: $zip"

# Установщик — если установлен Inno Setup (ищем компилятор ISCC)
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DAppVersion=$version" "installer\freelancedesk.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup завершился с ошибкой" }
    Write-Host "Установщик: dist\FreelanceDesk-$version-Setup.exe"
} else {
    Write-Host "Inno Setup не найден — установщик пропущен"
}
