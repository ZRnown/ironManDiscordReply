#!/usr/bin/env python3
"""
Discord自动回复工具运行脚本
"""

import sys
import os
from pathlib import Path

def main():
    # 1. 路径设置
    project_root = Path(__file__).parent
    src_dir = project_root / "src"
    sys.path.insert(0, str(src_dir))

    # 2. 依赖检查
    try:
        import discord
        import PySide6

        # 移除了对 Intents 的检查，因为 discord.py-self 2.0+ 已经废弃了它
        print(f"Discord 库版本: {getattr(discord, '__version__', '未知')}")
        print("环境依赖检查通过。")

    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install discord.py-self PySide6 typing-extensions")
        return

    # 3. 启动 GUI
    try:
        from src.gui import main as gui_main
        gui_main()
    except Exception as e:
        print(f"程序崩溃: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()