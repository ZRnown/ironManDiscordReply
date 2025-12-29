#!/usr/bin/env python3
"""
Discord 自动回复工具
支持多账号、多规则的Discord自动回复桌面应用
"""

import sys
import os

# 添加src目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gui import main
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import gui
    main = gui.main

if __name__ == "__main__":
    # 直接调用 main()，因为 gui.main() 是同步的 (app.exec())
    # 不要使用 asyncio.run()，因为 PySide6 的事件循环接管了主线程
    main()
