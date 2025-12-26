# Windows环境构建指南

## 🚀 在Windows上构建Discord自动回复工具

### 前置要求

1. **Python 3.11+**
   - 下载: https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **Git (可选)**
   - 下载项目代码需要Git
   - 下载: https://git-scm.com/downloads

### 📦 安装步骤

#### 步骤1: 下载项目

```cmd
# 克隆项目
git clone https://github.com/yourusername/discord-auto-reply.git
cd discord-auto-reply
```

或者直接下载ZIP包并解压。

#### 步骤2: 安装依赖

**重要**: 在Windows环境中，需要确保所有依赖都正确安装。

```cmd
# 升级pip
python -m pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt

# 验证安装
python -c "import discord, PySide6, pyinstaller; print('All dependencies installed successfully')"
```

#### 步骤3: 构建应用程序

```cmd
# 构建Windows可执行文件
python build.py --target windows
```

构建过程会显示详细的进度信息：

```
Discord Auto Reply Tool Builder
==================================================
Python version: 3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]
Target platform: windows
Checking dependencies...
[OK] PyInstaller is installed
[OK] discord.py-self is installed
[OK] PySide6 is installed

Cleaning build files...
[CLEAN] Removed build directory
[CLEAN] Removed dist directory

Using Windows build configuration
Executing command: pyinstaller --onefile --windowed --clean --name DiscordAutoReply --add-data config;config src/main.py
Running building application...
[SUCCESS] building application completed

==================================================
[SUCCESS] Build completed!

Output files:
  DiscordAutoReply.exe: 52.34 MB
```

### 🛠️ 故障排除

#### 问题1: PySide6安装失败

**错误信息**:
```
ERROR: Could not install packages due to an environment error
```

**解决方案**:
```cmd
# 使用管理员权限运行命令提示符
# 或者使用以下命令

# 清理pip缓存
pip cache purge

# 使用国内镜像
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 或者逐个安装
pip install discord.py-self
pip install PySide6
pip install pyinstaller
```

#### 问题2: 构建过程中出错

**错误信息**: 各种PyInstaller错误

**解决方案**:
```cmd
# 清理之前的构建文件
rd /s /q build dist
del DiscordAutoReply.spec

# 重新构建
python build.py --target windows
```

#### 问题3: 杀毒软件拦截

Windows Defender或其他杀毒软件可能会误报PyInstaller生成的文件。

**解决方案**:
1. 在构建前暂时关闭实时保护
2. 构建完成后添加到信任区
3. 或者在文件属性中取消锁定

#### 问题4: 缺少Visual C++ Redistributable

**错误信息**: `MSVCP140.dll missing`

**解决方案**:
下载并安装 Visual C++ Redistributable:
https://aka.ms/vs/17/release/vc_redist.x64.exe

### 📁 输出文件

构建成功后，`dist`文件夹中会包含：

```
dist/
├── DiscordAutoReply.exe    # 主程序 (约50MB)
└── Windows使用说明.md     # 使用指南
```

### 🧪 测试构建结果

1. **双击运行** `DiscordAutoReply.exe`
2. **检查界面** 是否正常显示
3. **测试功能** ：
   - 添加账号
   - 配置规则
   - 启动监听

### 📊 构建规格

- **Python版本**: 3.11+
- **构建工具**: PyInstaller 6.3.0
- **GUI框架**: PySide6 6.8.0.2
- **Discord库**: discord.py-self 2.0.1+
- **输出格式**: 单文件exe，无需安装
- **文件大小**: ~50MB (包含所有依赖)

### 💡 高级选项

#### 自定义构建

```cmd
# 不清理临时文件（用于调试）
python build.py --target windows

# 查看更多选项
python build.py --help
```

#### 环境变量

```cmd
# 设置PyInstaller缓存目录
set PYINSTALLER_CACHE_DIR=%TEMP%\pyinstaller_cache

# 增加构建超时时间（如果机器较慢）
set PYINSTALLER_TIMEOUT=300
```

### 🔄 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| PySide6安装失败 | 网络或权限问题 | 使用管理员权限或国内镜像 |
| 构建时间过长 | 机器性能不足 | 等待完成或使用更快的机器 |
| 文件被杀毒软件删除 | 误报 | 暂时关闭实时保护 |
| 运行时缺少dll | 缺少运行库 | 安装VC++ Redistributable |
| 界面显示异常 | DPI缩放问题 | 调整显示设置 |

### 📞 获取帮助

如果遇到无法解决的问题：

1. **查看构建日志**：完整的错误信息
2. **检查Python版本**：确保3.11+
3. **验证依赖安装**：逐个测试导入
4. **尝试最小化构建**：移除不必要的依赖

---

**🎉 现在您可以在Windows环境中成功构建Discord自动回复工具了！**
