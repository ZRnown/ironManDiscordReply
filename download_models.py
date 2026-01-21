#!/usr/bin/env python3
"""
手动下载AI模型脚本
用于预先下载DINOv2和YOLOv8模型，避免程序运行时下载
"""

import os
import sys
import argparse
from pathlib import Path

def download_dinov2_model(model_name="facebook/dinov2-small", cache_dir="models"):
    """下载DINOv2模型"""
    try:
        print(f"正在下载DINOv2模型: {model_name}")
        print(f"缓存目录: {cache_dir}")

        from transformers import AutoImageProcessor, AutoModel

        # 创建缓存目录
        os.makedirs(cache_dir, exist_ok=True)

        print("下载图像处理器...")
        processor = AutoImageProcessor.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False,
            use_fast=True  # 使用快速处理器
        )

        print("下载模型权重...")
        model = AutoModel.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )

        print(f"✅ DINOv2模型 {model_name} 下载完成!")
        print(f"模型保存在: {cache_dir}")

        # 显示模型大小
        model_dir = os.path.join(cache_dir, model_name.replace('/', '--'))
        if os.path.exists(model_dir):
            total_size = 0
            for file in Path(model_dir).rglob('*'):
                if file.is_file():
                    total_size += file.stat().st_size

            size_mb = total_size / (1024 * 1024)
            print(f"模型总大小: {size_mb:.1f} MB")

        return True

    except Exception as e:
        print(f"❌ DINOv2模型下载失败: {e}")
        return False

def download_yolo_model(cache_dir="models"):
    """下载YOLOv8模型"""
    try:
        print("正在下载YOLOv8-Nano模型...")
        print(f"缓存目录: {cache_dir}")

        from ultralytics import YOLO

        # 创建缓存目录
        os.makedirs(cache_dir, exist_ok=True)

        model_path = os.path.join(cache_dir, 'yolov8n.pt')
        print(f"下载到: {model_path}")

        # 下载模型
        model = YOLO('yolov8n.pt')

        # 保存到指定位置
        model.save(model_path)

        print("✅ YOLOv8-Nano模型下载完成!")
        print(f"模型保存在: {model_path}")

        # 显示文件大小
        if os.path.exists(model_path):
            size_mb = os.path.getsize(model_path) / (1024 * 1024)
            print(f"模型大小: {size_mb:.1f} MB")

        return True

    except Exception as e:
        print(f"❌ YOLOv8模型下载失败: {e}")
        return False

def check_dependencies():
    """检查依赖是否安装"""
    print("检查依赖...")

    missing_deps = []

    try:
        import transformers
        print(f"✅ transformers: {transformers.__version__}")
    except ImportError:
        missing_deps.append("transformers")

    try:
        import torch
        print(f"✅ torch: {torch.__version__}")
    except ImportError:
        missing_deps.append("torch")

    try:
        import ultralytics
        print(f"✅ ultralytics: {ultralytics.__version__}")
    except ImportError:
        missing_deps.append("ultralytics")

    if missing_deps:
        print("❌ 缺少以下依赖，请先安装:")
        for dep in missing_deps:
            print(f"  pip install {dep}")
        print("\n或者运行: pip install -r requirements.txt")
        return False

    return True

def main():
    parser = argparse.ArgumentParser(description='下载AI模型')
    parser.add_argument('--model', choices=['dinov2-small', 'dinov2-base', 'yolo', 'all'],
                       default='all', help='要下载的模型 (默认: all)')
    parser.add_argument('--cache-dir', default='models',
                       help='模型缓存目录 (默认: models)')
    parser.add_argument('--use-fast', action='store_true', default=True,
                       help='使用快速图像处理器')

    args = parser.parse_args()

    print("=" * 50)
    print("AI模型下载工具")
    print("=" * 50)

    # 检查依赖
    if not check_dependencies():
        return False

    success_count = 0
    total_count = 0

    # 下载DINOv2模型
    if args.model in ['dinov2-small', 'dinov2-base', 'all']:
        total_count += 1

        model_name = f"facebook/{args.model}" if args.model != 'all' else "facebook/dinov2-small"

        if args.model == 'dinov2-base':
            model_name = "facebook/dinov2-base"
        elif args.model == 'dinov2-small':
            model_name = "facebook/dinov2-small"
        else:  # all or dinov2-small
            model_name = "facebook/dinov2-small"

        print(f"\n下载 {model_name}...")
        if download_dinov2_model(model_name, args.cache_dir):
            success_count += 1

    # 下载YOLO模型
    if args.model in ['yolo', 'all']:
        total_count += 1
        print("\n下载 YOLOv8-Nano...")
        if download_yolo_model(args.cache_dir):
            success_count += 1

    print("\n" + "=" * 50)
    if success_count == total_count:
        print("🎉 所有模型下载完成!")
        print(f"模型保存在: {args.cache_dir}")
        print("\n现在可以运行程序: python run.py")
        return True
    else:
        print(f"❌ 下载完成: {success_count}/{total_count}")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n下载已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 下载过程中出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
