# -*- mode: python ; coding: utf-8 -*-
# DishBoard PyInstaller spec — cross-platform (macOS + Windows)
# macOS build:   ./build.sh
# Windows build: pyinstaller DishBoard.spec --clean -y

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))

# Auto-read version from utils/version.py so the bundle always matches
from utils.version import APP_VERSION
_v = APP_VERSION.lstrip("v")                                           # e.g. "0.71"
_build = str(int(_v.split(".")[0]) * 100 + int(_v.split(".")[1]))      # "44"

# Dynamic mf2py data path — works regardless of Python version or install location
import mf2py as _mf2py
_mf2py_backcompat = os.path.join(os.path.dirname(_mf2py.__file__), "backcompat-rules")

if sys.platform == "darwin":
    _icon_file = "assets/icons/icon.icns"
    _keyring_backend_hidden = ["keyring.backends.macOS"]
elif sys.platform.startswith("win"):
    _icon_file = "assets/icons/icon.ico"
    _keyring_backend_hidden = ["keyring.backends.Windows"]
else:
    _icon_file = "assets/icons/DishBoard-darkicon.png"
    _keyring_backend_hidden = []

# recipe_scrapers has 200+ site-specific scrapers loaded dynamically by hostname.
# PyInstaller misses them with a simple hiddenimport — collect every submodule.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
_recipe_scrapers_mods = collect_submodules('recipe_scrapers')
_recipe_scrapers_data = collect_data_files('recipe_scrapers')

block_cipher = None

a = Analysis(
    ['DishBoard.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Read-only assets bundled inside the .app
        ('assets/styles', 'assets/styles'),
        ('assets/icons',  'assets/icons'),
        ('assets/metadata', 'assets/metadata'),
        ('assets/prompts', 'assets/prompts'),
        # mf2py (dependency of extruct → recipe_scrapers) has a non-Python data dir
        # IMPORTANT: dishboard.db and config.json must NEVER appear here.
        # User data is written to OS-specific app-data folders at runtime.
        (_mf2py_backcompat, 'mf2py/backcompat-rules'),
        # Include any data files bundled with recipe_scrapers itself
        *_recipe_scrapers_data,
    ],
    hiddenimports=[
        # SSL certificates for the requests library (needed in frozen .app)
        'certifi',
        # recipe-scrapers: top-level package + ALL site-specific scraper submodules
        'recipe_scrapers',
        *_recipe_scrapers_mods,
        # qt_material needs its XML theme files found at runtime
        'qt_material',
        # qtawesome loads font data lazily
        'qtawesome',
        # PySide6 extras not always auto-detected
        'PySide6.QtSvg',
        'PySide6.QtXml',
        'PySide6.QtNetwork',
        # Supabase auth + cloud sync
        'supabase',
        'supabase._sync',
        'supabase._sync.client',
        'gotrue',
        'gotrue._sync',
        'httpx',
        'postgrest',
        'postgrest._sync',
        'storage3',
        'realtime',
        # macOS Keychain session persistence
        'keyring',
        'keyring.backends',
        *_keyring_backend_hidden,
        # Auth + sync modules
        'auth',
        'auth.supabase_client',
        'auth.session_manager',
        'auth.cloud_sync',
        'auth.oauth_server',
        'utils.cloud_sync_service',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['dotenv', 'python-dotenv'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DishBoard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window when double-clicked
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,        # None = current arch (use 'universal2' for fat binary)
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DishBoard',
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name='DishBoard.app',
        icon='assets/icons/icon.icns',
        bundle_identifier='com.tomslater.dishboard',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': _v,
            'CFBundleVersion': _build,
            'CFBundleDisplayName': 'DishBoard',
            'CFBundleName': 'DishBoard',
            'LSApplicationCategoryType': 'public.app-category.food-and-drink',
            'NSAppleEventsUsageDescription':
                'DishBoard uses AppleScript to export meals to Apple Calendar.',
            'NSCalendarsUsageDescription':
                'DishBoard can add planned meals to your Apple Calendar.',
        },
    )
