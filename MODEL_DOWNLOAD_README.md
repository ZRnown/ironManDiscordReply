# AI模型下载指南

本项目使用以下AI模型，需要预先下载以获得最佳体验：

## 🔧 快速下载脚本

### 方法1：使用自动下载脚本（推荐）

```bash
# 下载所有模型
python download_models.py

# 仅下载DINOv2-small模型
python download_models.py --model dinov2-small

# 仅下载YOLOv8模型
python download_models.py --model yolo

# 指定自定义缓存目录
python download_models.py --cache-dir /path/to/models
```

### 方法2：手动下载

#### DINOv2模型下载

DINOv2模型托管在Hugging Face上，可以使用以下方法下载：

**选项A：使用Hugging Face CLI（推荐）**
```bash
# 安装Hugging Face CLI
pip install huggingface_hub

# 下载DINOv2-small (推荐，384维，约346MB)
huggingface-cli download facebook/dinov2-small --local-dir models/dinov2-small

# 下载DINOv2-base (更高准确率，768维，约1.1GB)
huggingface-cli download facebook/dinov2-base --local-dir models/dinov2-base
```

**选项B：使用Git LFS**
```bash
# 克隆仓库
git lfs install
git clone https://huggingface.co/facebook/dinov2-small
mv dinov2-small models/
```

**选项C：浏览器下载**
1. 访问 [DINOv2-small](https://huggingface.co/facebook/dinov2-small)
2. 下载所有文件到 `models/dinov2-small/` 目录

#### YOLOv8模型下载

```bash
# 直接下载YOLOv8-Nano模型 (约6MB)
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt -O models/yolov8n.pt

# 或者使用curl
curl -L https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt -o models/yolov8n.pt
```

## 📁 文件结构

下载完成后，你的 `models/` 目录结构应该如下：

```
models/
├── dinov2-small/          # DINOv2-small模型文件
│   ├── config.json
│   ├── pytorch_model.bin
│   ├── preprocessor_config.json
│   └── ...
└── yolov8n.pt            # YOLOv8-Nano模型文件
```

## ⚙️ 配置说明

### 模型路径配置

在 `config/image_search_config.py` 中配置：

```python
IMAGE_SEARCH_CONFIG = {
    'model_cache_dir': 'models',              # 模型缓存目录
    'yolo_model_path': 'models/yolov8n.pt',   # YOLO模型路径
    'dinov2_model': 'facebook/dinov2-small',  # DINOv2模型名称
}
```

### 内存和性能优化

- **DINOv2-small**: 推荐用于大多数应用，内存占用约1.5GB
- **DINOv2-base**: 更高准确率，内存占用约3GB
- **CPU模式**: 所有模型都在CPU上运行，无需GPU

## 🚀 启动程序

模型下载完成后，直接启动程序：

```bash
python run.py
```

程序会自动检测本地模型文件并加载，无需重新下载。

## 🔍 故障排除

### 模型下载失败

1. **网络问题**: 检查网络连接，尝试使用代理
2. **磁盘空间**: 确保有足够的磁盘空间（至少2GB）
3. **权限问题**: 确保对models目录有写入权限

### 模型加载失败

1. **检查文件完整性**: 确认所有模型文件都已正确下载
2. **路径配置**: 确认 `image_search_config.py` 中的路径正确
3. **依赖版本**: 确保安装了正确的依赖版本

### 性能问题

- 如果内存不足，使用DINOv2-small而不是DINOv2-base
- 关闭YOLO预处理可以节省内存：`'use_yolo_crop': False`

## 📊 模型规格

| 模型 | 大小 | 向量维度 | 内存占用 | 准确率 |
|------|------|----------|----------|--------|
| DINOv2-small | ~346MB | 384 | ~1.5GB | 高 |
| DINOv2-base | ~1.1GB | 768 | ~3GB | 很高 |
| YOLOv8-Nano | ~6MB | - | ~50MB | 中等 |

## 💡 提示

- 首次运行时会自动下载模型，后续运行会使用本地缓存
- 模型文件较大，建议使用稳定的网络下载
- 可以同时下载多个模型版本，根据需要选择使用
