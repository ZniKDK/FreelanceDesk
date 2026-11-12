# Сборка FreelanceDesk.exe через PyInstaller.
# Запуск: .\build.ps1  (или: pyinstaller freelancedesk.spec --noconfirm)
#
# Сборка «папкой» (onedir): exe + папка _internal с Python и Qt.
# Такой вариант запускается быстрее, чем один большой exe, который
# каждый раз распаковывается во временную папку.

block_cipher = None

analysis = Analysis(
    ["main.py"],
    pathex=["src"],
    # Файлы программы, которые нужны во время работы
    datas=[
        ("migrations", "migrations"),
        ("resources", "resources"),
    ],
    hiddenimports=[],
    # Модули, которые программе не нужны, — меньше размер сборки
    excludes=["tkinter", "unittest", "pytest", "PyQt6.QtWebEngineCore",
              "PyQt6.QtMultimedia", "PyQt6.QtQml", "PyQt6.QtQuick",
              "PyQt6.Qt3DCore", "PyQt6.QtBluetooth"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="FreelanceDesk",
    icon="resources/app.ico",
    console=False,  # без чёрного окна консоли
    upx=False,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    name="FreelanceDesk",
    upx=False,
)
