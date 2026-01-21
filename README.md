# Discord 自动回复工具

支持多账号、多规则的Discord自动回复桌面应用。

## 功能特性

### 基础功能
- ✅ 多Discord账号同时运行
- ✅ 灵活的自动回复规则（关键词匹配、精确匹配、正则表达式）
- ✅ 可设置过滤关键词（例如 `http`）避免触发回复
- ✅ 账号轮换机制，避免频率限制
- ✅ 现代化的图形界面
- ✅ 配置导入导出

## 系统要求

- **操作系统**: Windows 10+ / macOS 10.15+
- **网络**: 稳定的互联网连接

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 启动程序

```bash
python run.py
```

### 2. 配置Discord账号

1. 在"账号管理"标签页中点击"添加账号"
2. 输入Discord Token（支持用户Token和Bot Token）
3. 验证Token有效性
4. 启用账号

### 3. 配置自动回复规则

1. 在"规则管理"标签页中点击"添加规则"
2. 设置关键词和回复内容
3. 选择匹配类型和目标频道
4. 配置延迟时间和过滤关键词（例如 `http`）

## 配置说明

### 基础配置 (`config/config.json`)
- 账号信息和规则设置

## 打包部署

### Windows打包
```bash
python build.py --target windows
```

### macOS打包
```bash
python build.py --target mac
```

## 安全注意事项

⚠️ **重要提醒**
- 妥善保管Discord Token，不要泄露
- 定期更新Token（Token会过期）
- 注意服务器的使用条款
- 控制自动回复频率，避免被限制

## 故障排除

### 常见问题

1. **Token无效**
   - 检查Token格式是否正确
   - 确认Token未过期
   - 验证网络连接

## 更新日志

### v1.0.0
- ✅ 基础自动回复功能
- ✅ 多账号支持
- ✅ 规则管理系统
- ✅ 图形界面

## 技术栈

- **GUI**: PySide6 (Qt)
- **Discord**: discord.py-self
- **打包**: PyInstaller

## 许可证

本项目仅供学习和个人使用，请遵守相关服务条款。
