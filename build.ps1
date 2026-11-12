# Сборка FreelanceDesk для Windows: dist\FreelanceDesk\FreelanceDesk.exe
# и архив dist\FreelanceDesk-<версия>-windows.zip для раздачи.
#
# Запуск из папки проекта:  .\build.ps1
# (если PowerShell запрещает скрипты: powershell -ExecutionPolicy Bypass -File build.ps1)

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"

# Версия — из пакета, чтобы не дублировать её вручную
$version = & $python -c "import sys; sys.path.insert(0, 'src'); import freelancedesk; print(freelancedesk.__version__)"
Write-Host "Сборка FreelanceDesk $version"

& $python -m pip install --quiet "pyinstaller>=6.10"
& $python -m PyInstaller freelancedesk.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }

$zip = "dist\FreelanceDesk-$version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\FreelanceDesk" -DestinationPath $zip
Write-Host "Готово: dist\FreelanceDesk\FreelanceDesk.exe и $zip"
