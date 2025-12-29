import sys
import os

print("Python 搜索路径:", sys.path)

try:
    import discord
    print("\n找到 discord 模块！")
    print("❌ '内鬼'文件位置:", discord.__file__)
    print("请删除上面显示的这个文件或文件夹（如果它不在 site-packages 目录内）！")
except ImportError:
    print("\n✅ 没有找到 discord 模块 (这是正常的，因为你刚卸载了它)")
except Exception as e:
    print(f"\n❌ 加载出错: {e}")