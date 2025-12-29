#!/usr/bin/env python3
"""
Discord Auto Reply Tool Build Script
Supports Mac and Windows platform packaging
Requirements:
- discord.py-self >= 2.0.0
- typing-extensions >= 4.0.0
- PySide6 == 6.8.0.2
- pyinstaller == 6.3.0
- shiboken6 == 6.8.0.2
"""

import os
import sys
import platform
import subprocess
from pathlib import Path


def run_command(command, description):
    """Run command and display status"""
    print(f"Running {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"[SUCCESS] {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return False


def check_dependencies():
    """Check dependencies"""
    print("Checking dependencies...")

    try:
        import PyInstaller
        print(f"[OK] PyInstaller is installed ({PyInstaller.__version__})")
    except ImportError:
        print("[ERROR] PyInstaller not installed, run: pip install pyinstaller==6.3.0")
        return False

    try:
        import discord
        print(f"[OK] discord.py-self is installed ({discord.__version__})")
    except ImportError:
        print("[ERROR] discord.py-self not installed, run: pip install discord.py-self")
        return False

    try:
        import PySide6
        print(f"[OK] PySide6 is installed ({PySide6.__version__})")
    except ImportError:
        print("[ERROR] PySide6 not installed, run: pip install PySide6==6.8.0.2")
        return False

    try:
        import typing_extensions
        print("[OK] typing-extensions is installed")
    except ImportError:
        print("[ERROR] typing-extensions not installed, run: pip install typing-extensions>=4.0.0")
        return False

    return True


def clean_build():
    """Clean build files"""
    print("Cleaning build files...")

    dirs_to_clean = ["build", "dist"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            import shutil
            shutil.rmtree(dir_name)
            print(f"[CLEAN] Removed {dir_name} directory")

    # Clean spec file cache
    spec_files = ["DiscordAutoReply.spec"]
    for spec_file in spec_files:
        if os.path.exists(spec_file):
            os.remove(spec_file)
            print(f"[CLEAN] Removed {spec_file}")


def build_app(target_platform="auto"):
    """构建应用程序"""
    if target_platform == "auto":
        system = platform.system().lower()
    else:
        system = target_platform.lower()

    print(f"Target platform: {system}")

    # Choose spec file based on platform
    if system == "windows":
        spec_template = "DiscordAutoReply-windows.spec"
        if os.path.exists(spec_template):
            # Use Windows-specific spec file
            spec_file = spec_template
            print(f"Using Windows-specific spec file: {spec_template}")
            command_str = f"pyinstaller --clean --noconfirm {spec_file}"
            print(f"Executing command: {command_str}")
            return run_command(command_str, "building Windows application")

    # Create spec file for better module control (for macOS and other platforms)
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_all

# Add src directory to path
sys.path.insert(0, os.path.join(SPECPATH, 'src'))

block_cipher = None

# Define the main script
main_script = os.path.join(SPECPATH, 'src', 'main.py')

# Collect PySide6 and shiboken6
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')
shiboken6_datas, shiboken6_binaries, shiboken6_hiddenimports = collect_all('shiboken6')

# Core hidden imports
hidden_imports = [
    'discord_client',
    'config_manager',
    'gui',
    'discord.ext.commands',  # 确保commands扩展被包含
    'discord.ext.tasks',     # 如果用到tasks
] + pyside6_hiddenimports + shiboken6_hiddenimports

# Data files - 只包含必要的配置文件
data_files = []
if os.path.exists('config'):
    data_files.append(('config', 'config'))

# 移除不必要的assets和src目录打包

a = Analysis(
    [main_script],
    pathex=[SPECPATH],
    binaries=pyside6_binaries + shiboken6_binaries,
    datas=data_files + pyside6_datas + shiboken6_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # --- 标准库垃圾 ---
        'tkinter', 'unittest', 'pdb', 'pydoc', 'test', 'distutils', 'email.test',

        # --- 常用科学计算库 (如果有残留) ---
        'numpy', 'matplotlib', 'pandas', 'scipy', 'PIL', 'cv2', 'pygame',

        # --- 开发工具 ---
        'pip', 'setuptools', 'wheel',

        # --- PySide6/Qt 巨型无用模块 (关键减重区) ---
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',  # 浏览器内核，最大毒瘤
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',      # QML 相关，用的是 QtWidgets，不需要这个
        'PySide6.QtSql',               # 除非用了 QtSql，否则排除
        'PySide6.QtTest',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtOpenGL',            # 简单的 GUI 不需要 OpenGL
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtPrintSupport',
        'PySide6.QtQuick3D',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSvg',               # 如果没用 SVG 图标可排除
        'PySide6.QtSvgWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtWebSockets',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# === 新增：暴力过滤 Qt 垃圾文件 ===
def filter_qt_bloat(toc):
    """过滤掉不需要的 Qt 文件"""
    new_toc = []
    for dest, source, type_ in toc:
        # 1. 过滤翻译文件 (*.qm)，除非你需要多语言
        if source and 'translations' in source and source.endswith('.qm'):
            # 保留中文和英文(可选)
            if 'zh_' not in source and 'en_' not in source:
                continue

        # 2. 过滤掉 imageformats 中不常用的格式
        if 'imageformats' in dest:
            # 只保留 jpg, png, ico
            if not (dest.endswith('qjpeg.dll') or dest.endswith('qpng.dll') or dest.endswith('qico.dll')):
                continue

        # 3. 再次确保 WebEngine 相关的 DLL 不被打包 (双重保险)
        if 'Qt6WebEngine' in dest or 'Qt6Quick' in dest or 'Qt6Qml' in dest or 'Qt6OpenGL' in dest:
            continue

        new_toc.append((dest, source, type_))
    return new_toc

# 应用过滤
a.binaries = filter_qt_bloat(a.binaries)
a.datas = filter_qt_bloat(a.datas)
# ===================================

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DiscordAutoReply',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # 启用strip以减小文件大小
    upx=False,  # 在Windows上禁用UPX，避免DLL加载问题
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''

    # Write spec file
    spec_file = "DiscordAutoReply.spec"
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)

    # Base PyInstaller command using spec file
    cmd = [
        "pyinstaller",
        "--clean",  # Clean temporary files
        "--noconfirm",
        spec_file,  # Use spec file (spec file defines output mode)
    ]

    # Run PyInstaller
    command_str = " ".join(cmd)
    print(f"Executing command: {command_str}")

    return run_command(command_str, "building application")


def create_dmg():
    """Create DMG file for macOS"""
    if platform.system().lower() != "darwin":
        return True

    print("Creating DMG file for macOS...")

    app_path = "dist/DiscordAutoReply.app"
    dmg_path = "dist/DiscordAutoReply.dmg"

    if not os.path.exists(app_path):
        print("[ERROR] .app file not found")
        return False

    # Use hdiutil to create DMG
    cmd = f"hdiutil create -volname 'DiscordAutoReply' -srcfolder {app_path} -ov -format UDZO {dmg_path}"

    return run_command(cmd, "creating DMG file")


def main():
    """主函数"""
    print("Discord Auto Reply Tool Builder")
    print("=" * 50)

    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Build Discord auto reply tool')
    parser.add_argument('--target', choices=['windows', 'mac', 'auto'],
                       default='auto', help='Target platform (default: auto-detect)')
    parser.add_argument('--no-dmg', action='store_true',
                       help='Do not create DMG file for macOS')
    args = parser.parse_args()

    # Check Python version
    if sys.version_info < (3, 8):
        print("[ERROR] Python 3.8 or higher is required")
        return False

    print(f"Python version: {sys.version}")
    print(f"Target platform: {args.target}")

    # Check dependencies
    if not check_dependencies():
        return False

    # Switch to project root directory
    project_root = Path(__file__).parent
    os.chdir(project_root)

    # Clean old build files
    clean_build()

    # Build application
    if not build_app(args.target):
        return False

    # Create DMG for macOS (if not Windows target and not disabled)
    if not args.no_dmg and platform.system().lower() == "darwin":
        if not create_dmg():
            return False

    print("\n" + "=" * 50)
    print("[SUCCESS] Build completed!")

    # Display output file information
    dist_dir = Path("dist")
    if dist_dir.exists():
        print("\nOutput files:")
        for file_path in dist_dir.iterdir():
            if file_path.is_file():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                print(f"  {file_path.name}: {size_mb:.2f} MB")

    print("\nUsage instructions:")
    print("1. Run the generated executable file")
    print("2. Add Discord accounts and auto-reply rules in the program")
    print("3. Click start to begin monitoring and auto-replying")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
