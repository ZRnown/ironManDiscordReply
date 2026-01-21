#!/usr/bin/env python3
"""
向量索引管理模块
基于FAISS的向量相似度搜索
"""

import os
import sys
import numpy as np
import logging
from typing import List, Tuple, Dict, Any, Optional
import json

# 单例模式确保索引只加载一次
class VectorIndexManager:
    """向量索引管理器 - 单例模式"""

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
            self.index = None
            self.id_to_index = {}  # 图片ID到索引位置的映射
            self.index_to_id = {}  # 索引位置到图片ID的映射
            self.dimension = 384  # 默认向量维度
            self._initialized = True

    def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化向量索引"""
        try:
            self.config = config
            self.dimension = config.get('vector_dim', 384)

            # 尝试加载FAISS
            try:
                import faiss
                self.faiss = faiss
            except ImportError:
                self.logger.error("FAISS未安装，请运行: pip install faiss-cpu")
                return False

            # 创建或加载索引
            if not self._load_or_create_index():
                return False

            self.logger.info("向量索引初始化完成")
            return True

        except Exception as e:
            self.logger.error(f"向量索引初始化失败: {e}")
            return False

    def _load_or_create_index(self) -> bool:
        """加载或创建FAISS索引"""
        try:
            index_file = self.config.get('index_file', 'config/vector_index.faiss')
            mapping_file = self.config.get('mapping_file', 'config/vector_mapping.json')

            if os.path.exists(index_file):
                # 加载现有索引
                self.logger.info(f"加载现有索引: {index_file}")
                self.index = self.faiss.read_index(index_file)

                # 加载ID映射
                if os.path.exists(mapping_file):
                    with open(mapping_file, 'r', encoding='utf-8') as f:
                        mapping_data = json.load(f)
                        self.id_to_index = mapping_data.get('id_to_index', {})
                        self.index_to_id = {int(k): v for k, v in mapping_data.get('index_to_id', {}).items()}

                self.logger.info(f"成功加载索引，包含 {len(self.id_to_index)} 个向量")
                return True

            else:
                # 创建新索引
                self.logger.info("创建新的FAISS索引")

                # 使用HNSW索引，参数优化
                M = self.config.get('hnsw_M', 32)  # 邻居数
                efConstruction = self.config.get('hnsw_efConstruction', 80)  # 构建时搜索深度

                # 创建HNSW索引，使用内积（归一化向量等同于余弦相似度）
                self.index = self.faiss.IndexHNSWFlat(self.dimension, M)
                self.index.hnsw.efConstruction = efConstruction

                # 设置搜索参数
                efSearch = self.config.get('hnsw_efSearch', 64)
                self.index.hnsw.efSearch = efSearch

                # 使用内积度量
                self.index.metric_type = self.faiss.METRIC_INNER_PRODUCT

                self.id_to_index = {}
                self.index_to_id = {}

                self.logger.info(f"创建HNSW索引，维度: {self.dimension}, M: {M}")
                return True

        except Exception as e:
            self.logger.error(f"索引加载/创建失败: {e}")
            return False

    def add_vector(self, vector: np.ndarray, image_id: str) -> bool:
        """添加向量到索引"""
        try:
            if vector.shape[0] != self.dimension:
                self.logger.error(f"向量维度不匹配: 期望 {self.dimension}, 实际 {vector.shape[0]}")
                return False

            # 检查是否已存在
            if image_id in self.id_to_index:
                self.logger.warning(f"向量已存在: {image_id}")
                return False

            # 确保是二维数组 (FAISS要求)
            if vector.ndim == 1:
                vector = vector.reshape(1, -1)

            # 添加到索引
            self.index.add(vector.astype(np.float32))

            # 更新映射
            index_pos = len(self.id_to_index)
            self.id_to_index[image_id] = index_pos
            self.index_to_id[index_pos] = image_id

            return True

        except Exception as e:
            self.logger.error(f"添加向量失败: {e}")
            return False

    def remove_vector(self, image_id: str) -> bool:
        """从索引中移除向量"""
        try:
            if image_id not in self.id_to_index:
                return False

            # FAISS不支持直接删除，我们需要重建索引
            # 这是一个简化的实现，生产环境可能需要更复杂的策略
            self.logger.warning(f"FAISS不支持直接删除向量: {image_id}，建议重建索引")
            return False

        except Exception as e:
            self.logger.error(f"移除向量失败: {e}")
            return False

    def search_similar(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """搜索相似向量"""
        try:
            if query_vector.shape[0] != self.dimension:
                self.logger.error(f"查询向量维度不匹配: 期望 {self.dimension}, 实际 {query_vector.shape[0]}")
                return []

            # 确保是二维数组
            if query_vector.ndim == 1:
                query_vector = query_vector.reshape(1, -1)

            # 执行搜索
            distances, indices = self.index.search(query_vector.astype(np.float32), min(top_k, self.index.ntotal))

            # 转换为结果列表
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx != -1 and idx in self.index_to_id:  # -1表示未找到
                    image_id = self.index_to_id[idx]
                    similarity = float(dist)  # 内积值即相似度
                    results.append((image_id, similarity))

            return results

        except Exception as e:
            self.logger.error(f"相似度搜索失败: {e}")
            return []

    def save_index(self) -> bool:
        """保存索引到磁盘"""
        try:
            index_file = self.config.get('index_file', 'config/vector_index.faiss')
            mapping_file = self.config.get('mapping_file', 'config/vector_mapping.json')

            # 创建目录
            os.makedirs(os.path.dirname(index_file), exist_ok=True)

            # 保存FAISS索引
            self.faiss.write_index(self.index, index_file)

            # 保存ID映射
            mapping_data = {
                'id_to_index': self.id_to_index,
                'index_to_id': self.index_to_id,
                'dimension': self.dimension,
                'total_vectors': len(self.id_to_index)
            }

            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"索引保存成功: {len(self.id_to_index)} 个向量")
            return True

        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")
            return False

    def rebuild_index(self) -> bool:
        """重建索引（清除所有数据）"""
        try:
            self.logger.info("重建向量索引...")

            # 清除现有数据
            self.id_to_index.clear()
            self.index_to_id.clear()

            # 重新创建索引
            M = self.config.get('hnsw_M', 32)
            efConstruction = self.config.get('hnsw_efConstruction', 80)
            efSearch = self.config.get('hnsw_efSearch', 64)

            self.index = self.faiss.IndexHNSWFlat(self.dimension, M)
            self.index.hnsw.efConstruction = efConstruction
            self.index.hnsw.efSearch = efSearch
            self.index.metric_type = self.faiss.METRIC_INNER_PRODUCT

            self.logger.info("索引重建完成")
            return True

        except Exception as e:
            self.logger.error(f"重建索引失败: {e}")
            return False

    def get_stats(self) -> Dict:
        """获取索引统计信息"""
        try:
            return {
                'total_vectors': len(self.id_to_index),
                'dimension': self.dimension,
                'index_type': 'HNSW',
                'metric': 'Inner Product',
                'memory_usage_mb': self.index.ntotal * self.dimension * 4 / (1024 * 1024) if self.index else 0
            }
        except Exception as e:
            return {'error': str(e)}

    def cleanup(self):
        """清理资源"""
        try:
            if self.index:
                # FAISS索引清理
                self.index.reset()
                del self.index

            self.id_to_index.clear()
            self.index_to_id.clear()

        except Exception as e:
            self.logger.error(f"清理索引资源失败: {e}")


# 全局实例 - 延迟初始化
_vector_index_instance = None


def get_vector_index_manager() -> VectorIndexManager:
    """获取向量索引管理器实例"""
    global _vector_index_instance
    if _vector_index_instance is None:
        _vector_index_instance = VectorIndexManager()
    return _vector_index_instance
