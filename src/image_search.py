#!/usr/bin/env python3
"""
图片搜索核心模块
基于DINOv2特征提取和FAISS向量检索的图片相似度搜索
"""

import os
import sys
import json
import numpy as np
import torch
from PIL import Image
import logging
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
import hashlib
import base64
from io import BytesIO

# 单例模式确保模型只加载一次
class ImageSearchManager:
    """图片搜索管理器 - 单例模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger(__name__)
            self.config = None
            self.image_processor = None
            self.vector_index = None
            self.image_database = {}  # 图片ID到关键词的映射
            self._initialized = True

    def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化图片搜索系统"""
        try:
            self.config = config
            self.logger.info("正在初始化图片搜索系统...")

            # 导入依赖模块
            from image_processor import get_image_processor
            from vector_index import get_vector_index_manager

            # 初始化图片处理器
            self.image_processor = get_image_processor()
            if not self.image_processor.initialize(config):
                self.logger.error("图片处理器初始化失败")
                return False

            # 初始化向量索引
            self.vector_index = get_vector_index_manager()
            if not self.vector_index.initialize(config):
                self.logger.error("向量索引初始化失败")
                return False

            # 加载图片数据库
            self._load_image_database()

            self.logger.info("图片搜索系统初始化完成")
            return True

        except Exception as e:
            self.logger.error(f"图片搜索系统初始化失败: {e}")
            return False

    def _load_image_database(self):
        """加载图片数据库"""
        try:
            db_file = self.config.get('database_file', 'config/image_database.json')
            if os.path.exists(db_file):
                with open(db_file, 'r', encoding='utf-8') as f:
                    self.image_database = json.load(f)
                self.logger.info(f"加载了 {len(self.image_database)} 个图片记录")
            else:
                self.image_database = {}
                self.logger.info("创建新的图片数据库")
        except Exception as e:
            self.logger.error(f"加载图片数据库失败: {e}")
            self.image_database = {}

    def _save_image_database(self):
        """保存图片数据库"""
        try:
            db_file = self.config.get('database_file', 'config/image_database.json')
            os.makedirs(os.path.dirname(db_file), exist_ok=True)
            with open(db_file, 'w', encoding='utf-8') as f:
                json.dump(self.image_database, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存图片数据库失败: {e}")

    def add_image(self, image_path: str, keywords: str, image_data: Optional[bytes] = None) -> bool:
        """添加图片到搜索库"""
        try:
            # 生成图片ID
            if image_data:
                image_id = hashlib.md5(image_data).hexdigest()
            else:
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                image_id = hashlib.md5(image_data).hexdigest()

            # 检查是否已存在
            if image_id in self.image_database:
                self.logger.warning(f"图片已存在: {image_id}")
                return False

            # 提取特征向量
            vector = self.image_processor.extract_features(image_path, image_data)
            if vector is None:
                self.logger.error(f"特征提取失败: {image_path}")
                return False

            # 添加到向量索引
            if not self.vector_index.add_vector(vector, image_id):
                self.logger.error(f"添加到向量索引失败: {image_id}")
                return False

            # 保存到数据库
            self.image_database[image_id] = {
                'keywords': keywords,
                'vector_shape': vector.shape,
                'added_time': str(np.datetime64('now'))
            }

            self._save_image_database()
            self.logger.info(f"成功添加图片: {image_id} - {keywords}")
            return True

        except Exception as e:
            self.logger.error(f"添加图片失败: {e}")
            return False

    def search_similar(self, image_path: str = None, image_data: bytes = None, top_k: int = 5) -> List[Dict]:
        """搜索相似图片"""
        try:
            # 提取特征向量
            vector = self.image_processor.extract_features(image_path, image_data)
            if vector is None:
                self.logger.error("特征提取失败")
                return []

            # 搜索相似向量
            results = self.vector_index.search_similar(vector, top_k)
            if not results:
                return []

            # 转换为结果格式
            search_results = []
            for image_id, similarity in results:
                if image_id in self.image_database:
                    search_results.append({
                        'image_id': image_id,
                        'keywords': self.image_database[image_id]['keywords'],
                        'similarity': float(similarity),
                        'confidence': float(similarity)  # 相似度作为置信度
                    })

            return search_results

        except Exception as e:
            self.logger.error(f"搜索相似图片失败: {e}")
            return []

    def remove_image(self, image_id: str) -> bool:
        """移除图片"""
        try:
            if image_id not in self.image_database:
                return False

            # 从向量索引中移除
            if not self.vector_index.remove_vector(image_id):
                self.logger.warning(f"从向量索引移除失败: {image_id}")

            # 从数据库中移除
            del self.image_database[image_id]
            self._save_image_database()

            self.logger.info(f"成功移除图片: {image_id}")
            return True

        except Exception as e:
            self.logger.error(f"移除图片失败: {e}")
            return False

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_images': len(self.image_database),
            'index_stats': self.vector_index.get_stats() if self.vector_index else {},
            'model_info': self.image_processor.get_model_info() if self.image_processor else {}
        }

    def save_index(self) -> bool:
        """保存索引到磁盘"""
        try:
            return self.vector_index.save_index() if self.vector_index else False
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")
            return False

    def cleanup(self):
        """清理资源"""
        try:
            if self.vector_index:
                self.vector_index.cleanup()
            if self.image_processor:
                self.image_processor.cleanup()
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")


# 全局实例 - 延迟初始化
_image_search_instance = None


def get_image_search_manager() -> ImageSearchManager:
    """获取图片搜索管理器实例"""
    global _image_search_instance
    if _image_search_instance is None:
        _image_search_instance = ImageSearchManager()
    return _image_search_instance
