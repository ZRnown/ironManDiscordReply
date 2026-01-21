#!/usr/bin/env python3
"""
图片处理器模块
包含DINOv2特征提取和YOLOv8主体检测裁剪功能
"""

import os
import sys
import numpy as np
import torch
from PIL import Image
import logging
from typing import Optional, Tuple, Dict, Any
import io

# 单例模式确保模型只加载一次
class ImageProcessor:
    """图片处理器 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.logger = logging.getLogger(__name__)
            self.config = None
            self.dinov2_model = None
            self.dinov2_processor = None
            self.yolo_model = None
            self.device = torch.device('cpu')
            self._initialized = True

    def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化图片处理器"""
        try:
            self.config = config
            self.logger.info("正在初始化图片处理器...")

            # 初始化DINOv2模型
            if not self._initialize_dinov2():
                return False

            # 初始化YOLO模型（如果启用）
            if config.get('use_yolo_crop', False):
                if not self._initialize_yolo():
                    self.logger.warning("YOLO初始化失败，将使用原图模式")

            self.logger.info("图片处理器初始化完成")
            return True

        except Exception as e:
            self.logger.error(f"图片处理器初始化失败: {e}")
            return False

    def _initialize_dinov2(self) -> bool:
        """初始化DINOv2模型"""
        try:
            from transformers import AutoImageProcessor, AutoModel

            model_name = self.config.get('dinov2_model', 'facebook/dinov2-small')
            cache_dir = self.config.get('model_cache_dir', 'models')
            os.makedirs(cache_dir, exist_ok=True)

            self.logger.info(f"正在加载DINOv2模型: {model_name}")
            self.logger.info(f"模型缓存目录: {cache_dir}")

            # 首先尝试从本地加载
            try:
                self.logger.info("尝试从本地文件加载模型...")
                self.dinov2_processor = AutoImageProcessor.from_pretrained(
                    model_name,
                    cache_dir=cache_dir,
                    local_files_only=True,
                    use_fast=True
                )

                self.dinov2_model = AutoModel.from_pretrained(
                    model_name,
                    cache_dir=cache_dir,
                    local_files_only=True
                )
                self.logger.info("✅ 成功从本地加载模型")

            except (OSError, ValueError) as e:
                # 本地没有文件，需要下载
                self.logger.warning(f"本地模型文件不存在，开始下载: {e}")
                self.logger.info("正在从Hugging Face下载模型，请稍候...")

                try:
                    self.dinov2_processor = AutoImageProcessor.from_pretrained(
                        model_name,
                        cache_dir=cache_dir,
                        local_files_only=False,
                        use_fast=True
                    )

                    self.dinov2_model = AutoModel.from_pretrained(
                        model_name,
                        cache_dir=cache_dir,
                        local_files_only=False
                    )
                    self.logger.info("✅ 模型下载完成")

                except Exception as download_error:
                    self.logger.error(f"模型下载失败: {download_error}")
                    return False

            # 确保模型在CPU上运行
            self.dinov2_model.to(self.device)
            self.dinov2_model.eval()

            self.logger.info("DINOv2模型加载成功")
            return True

        except Exception as e:
            self.logger.error(f"DINOv2模型初始化失败: {e}")
            return False

    def _initialize_yolo(self) -> bool:
        """初始化YOLOv8模型"""
        try:
            from ultralytics import YOLO

            model_path = self.config.get('yolo_model_path', 'models/yolov8n.pt')
            cache_dir = self.config.get('model_cache_dir', 'models')
            os.makedirs(cache_dir, exist_ok=True)

            # 检查本地模型文件
            if os.path.exists(model_path):
                self.logger.info(f"加载本地YOLO模型: {model_path}")
                self.yolo_model = YOLO(model_path)
                self.logger.info("✅ YOLOv8模型加载成功")
                return True
            else:
                self.logger.info(f"本地YOLO模型不存在，开始下载: {model_path}")
                try:
                    # 直接下载到指定路径
                    self.yolo_model = YOLO('yolov8n.pt')

                    # 保存到本地
                    if hasattr(self.yolo_model, 'save'):
                        self.yolo_model.save(model_path)
                        self.logger.info(f"✅ YOLO模型已保存到: {model_path}")

                    return True

                except Exception as download_error:
                    self.logger.error(f"YOLO模型下载失败: {download_error}")
                    return False

        except Exception as e:
            self.logger.error(f"YOLO模型初始化失败: {e}")
            return False

    def extract_features(self, image_path: str = None, image_data: bytes = None) -> Optional[np.ndarray]:
        """提取图片特征向量"""
        try:
            # 加载和预处理图片
            image = self._load_image(image_path, image_data)
            if image is None:
                return None

            # YOLO裁剪（如果启用）
            if self.config.get('use_yolo_crop', False) and self.yolo_model:
                image = self._crop_with_yolo(image)
                if image is None:
                    # 裁剪失败，使用原图
                    image = self._load_image(image_path, image_data)
                    if image is None:
                        return None

            # DINOv2特征提取
            return self._extract_dinov2_features(image)

        except Exception as e:
            self.logger.error(f"特征提取失败: {e}")
            return None

    def _load_image(self, image_path: str = None, image_data: bytes = None) -> Optional[Image.Image]:
        """加载图片"""
        try:
            if image_data:
                image = Image.open(io.BytesIO(image_data))
            elif image_path:
                image = Image.open(image_path)
            else:
                return None

            # 转换为RGB模式
            if image.mode != 'RGB':
                image = image.convert('RGB')

            return image

        except Exception as e:
            self.logger.error(f"图片加载失败: {e}")
            return None

    def _crop_with_yolo(self, image: Image.Image) -> Optional[Image.Image]:
        """使用YOLO进行主体检测和裁剪"""
        try:
            if not self.yolo_model:
                return image

            # 保存临时图片供YOLO处理
            temp_path = f"temp_yolo_{hash(str(image))}.jpg"
            image.save(temp_path, 'JPEG')

            try:
                # YOLO推理
                results = self.yolo_model(temp_path, conf=0.25, verbose=False)

                if not results or len(results) == 0:
                    self.logger.warning("YOLO未检测到任何物体")
                    return image

                result = results[0]
                if len(result.boxes) == 0:
                    self.logger.warning("YOLO未检测到边界框")
                    return image

                # 找到最大面积的检测框
                boxes = result.boxes.xyxy.cpu().numpy()
                areas = [(box[2] - box[0]) * (box[3] - box[1]) for box in boxes]
                max_area_idx = np.argmax(areas)
                best_box = boxes[max_area_idx]

                # 转换为整数坐标
                x1, y1, x2, y2 = map(int, best_box)

                # 向外扩展5%的边缘
                width, height = image.size
                margin_x = int((x2 - x1) * 0.05)
                margin_y = int((y2 - y1) * 0.05)

                x1 = max(0, x1 - margin_x)
                y1 = max(0, y1 - margin_y)
                x2 = min(width, x2 + margin_x)
                y2 = min(height, y2 + margin_y)

                # 裁剪图片
                cropped_image = image.crop((x1, y1, x2, y2))
                self.logger.info(f"YOLO裁剪成功: {best_box} -> ({x1},{y1},{x2},{y2})")

                return cropped_image

            finally:
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as e:
            self.logger.error(f"YOLO裁剪失败: {e}")
            return image  # 返回原图作为降级方案

    def _extract_dinov2_features(self, image: Image.Image) -> Optional[np.ndarray]:
        """使用DINOv2提取特征"""
        try:
            if not self.dinov2_model or not self.dinov2_processor:
                self.logger.error("DINOv2模型未初始化")
                return None

            # 预处理图片
            inputs = self.dinov2_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # 推理
            with torch.no_grad():
                outputs = self.dinov2_model(**inputs)

            # 提取CLS token (第一个token)
            cls_token = outputs.last_hidden_state[:, 0, :]  # [1, seq_len, hidden_size] -> [1, hidden_size]

            # 转换为numpy数组
            vector = cls_token.squeeze().cpu().numpy()

            # L2归一化
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm

            return vector.astype(np.float32)

        except Exception as e:
            self.logger.error(f"DINOv2特征提取失败: {e}")
            return None

    def get_model_info(self) -> Dict:
        """获取模型信息"""
        return {
            'dinov2_model': self.config.get('dinov2_model', 'unknown'),
            'use_yolo_crop': self.config.get('use_yolo_crop', False),
            'device': str(self.device),
            'vector_dim': 384 if 'small' in str(self.config.get('dinov2_model', '')) else 768
        }

    def cleanup(self):
        """清理资源"""
        try:
            if self.dinov2_model:
                del self.dinov2_model
            if self.dinov2_processor:
                del self.dinov2_processor
            if self.yolo_model:
                del self.yolo_model

            # 清理GPU缓存（如果有）
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")


# 全局实例 - 延迟初始化
_image_processor_instance = None


def get_image_processor() -> ImageProcessor:
    """获取图片处理器实例"""
    global _image_processor_instance
    if _image_processor_instance is None:
        _image_processor_instance = ImageProcessor()
    return _image_processor_instance
