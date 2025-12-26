#!/usr/bin/env python3
"""
Discord Auto Reply Tool Build Script
Supports Mac and Windows platform packaging
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
        print("[OK] PyInstaller is installed")
    except ImportError:
        print("[ERROR] PyInstaller not installed, run: pip install pyinstaller")
        return False

    try:
        import discord
        print("[OK] discord.py-self is installed")
    except ImportError:
        print("[ERROR] discord.py-self not installed, run: pip install discord.py-self")
        return False

    try:
        import PySide6
        print("[OK] PySide6 is installed")
    except ImportError:
        print("[ERROR] PySide6 not installed, run: pip install PySide6")
        return False

    # qasync不再需要，直接使用asyncio集成

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

    # Base PyInstaller command
    cmd = [
        "pyinstaller",
        "--onefile",  # Package as single file
        "--windowed",  # No console window
        "--clean",  # Clean temporary files
        "--name", "DiscordAutoReply",
    ]

    # Add platform-specific options
    if system == "darwin" or system == "mac":  # macOS
        cmd.extend([
            "--target-arch", "universal2",  # Universal binary
            "--osx-bundle-identifier", "com.discordautoreply.app",
        ])
        print("Using macOS build configuration")
    elif system == "windows" or system == "win":  # Windows
        cmd.extend([
            "--win-private-assemblies",  # Windows specific option
        ])
        print("Using Windows build configuration")
    else:
        print(f"Unsupported platform: {system}")
        return False

    # Add data files
    if os.path.exists("config"):
        if system == "windows":
            cmd.extend(["--add-data", "config;config"])
        else:  # macOS and others
            cmd.extend(["--add-data", "config:config"])

    if os.path.exists("assets"):
        if system == "windows":
            cmd.extend(["--add-data", "assets;assets"])
        else:  # macOS and others
            cmd.extend(["--add-data", "assets:assets"])

    # Add main file
    cmd.append("src/main.py")

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
