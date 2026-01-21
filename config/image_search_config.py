#!/usr/bin/env python3
"""
图片搜索配置文件
包含所有图片搜索相关的参数设置
"""

import os
from typing import Dict, Any

# 图片搜索配置
IMAGE_SEARCH_CONFIG = {
    # === 基础设置 ===
    'enabled': True,  # 是否启用图片搜索功能

    # === 模型配置 ===
    'dinov2_model': 'facebook/dinov2-small',  # DINOv2模型名称
    # 可选: 'facebook/dinov2-base' (更高准确率，但内存占用更大)

    'vector_dim': 384,  # 向量维度 (small=384, base=768)

    # === YOLO预处理配置 ===
    'use_yolo_crop': False,  # 是否启用YOLO主体检测裁剪
    'yolo_model_path': 'models/yolov8n.pt',  # YOLO模型路径
    'yolo_conf_threshold': 0.25,  # YOLO检测置信度阈值
    'yolo_padding_ratio': 0.05,  # 裁剪时向外扩展的比例 (5%)

    # === FAISS索引配置 ===
    'index_file': 'config/vector_index.faiss',  # FAISS索引文件路径
    'mapping_file': 'config/vector_mapping.json',  # ID映射文件路径
    'database_file': 'config/image_database.json',  # 图片数据库文件路径

    # HNSW索引参数 (针对百万级数据优化)
    'hnsw_M': 32,  # 每个节点的邻居数，影响索引大小和准确率
    'hnsw_efConstruction': 80,  # 构建时搜索深度，影响构建时间
    'hnsw_efSearch': 64,  # 查询时搜索深度，影响查询速度

    # === 搜索配置 ===
    'default_top_k': 5,  # 默认搜索返回数量
    'similarity_threshold': 0.8,  # 相似度阈值 (0.0-1.0)
    'max_search_results': 10,  # 最大搜索结果数量

    # === 模型缓存配置 ===
    'model_cache_dir': 'models',  # 模型缓存目录

    # === 性能配置 ===
    'batch_size': 32,  # 批量处理时的批大小
    'max_image_size': 1024,  # 图片最大尺寸 (像素)
    'jpeg_quality': 95,  # 保存图片时的JPEG质量

    # === 内存管理 ===
    'max_memory_gb': 2.0,  # 模型最大内存占用 (GB)
    'cleanup_interval': 3600,  # 清理间隔 (秒)

    # === Discord集成配置 ===
    'auto_search_images': True,  # 是否自动搜索Discord中的图片
    'reply_similarity_threshold': 0.85,  # 自动回复的相似度阈值
    'max_reply_keywords': 3,  # 回复时最多显示的关键词数量
    'reply_template': "我找到了相似图片！关键词：{keywords}",  # 回复模板

    # === 日志配置 ===
    'log_level': 'INFO',  # 日志级别
    'log_file': 'logs/image_search.log',  # 日志文件路径

    # === 调试配置 ===
    'debug_mode': False,  # 调试模式
    'save_processed_images': False,  # 是否保存处理后的图片
    'processed_images_dir': 'debug/processed_images',  # 处理后图片保存目录
}


def get_config() -> Dict[str, Any]:
    """获取配置字典"""
    return IMAGE_SEARCH_CONFIG.copy()


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """更新配置"""
    IMAGE_SEARCH_CONFIG.update(updates)
    return IMAGE_SEARCH_CONFIG.copy()


def save_config_to_file(filepath: str = 'config/image_search_config.json') -> bool:
    """保存配置到文件"""
    try:
        import json
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(IMAGE_SEARCH_CONFIG, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


def load_config_from_file(filepath: str = 'config/image_search_config.json') -> Dict[str, Any]:
    """从文件加载配置"""
    try:
        import json
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            IMAGE_SEARCH_CONFIG.update(loaded_config)
    except Exception as e:
        print(f"加载配置失败: {e}")
    return IMAGE_SEARCH_CONFIG.copy()


# 自动创建必要的目录
def ensure_directories():
    """确保必要的目录存在"""
    directories = [
        'models',
        'config',
        'logs',
        'debug/processed_images'
    ]

    for dir_path in directories:
        os.makedirs(dir_path, exist_ok=True)


# 初始化
ensure_directories()

# 注意：配置保存在Python文件中，不从外部JSON文件加载
# 如需修改配置，请直接编辑此文件中的 IMAGE_SEARCH_CONFIG 字典
