# 数据库备份系统使用说明

## 概述

这个备份系统可以自动备份你的 `pricing_system.db` 数据库文件，防止数据丢失。

## 功能特性

- ✅ **自动备份**: 每天定时备份数据库
- ✅ **数据验证**: 备份前验证数据库完整性
- ✅ **自动清理**: 保留最近7天的备份，自动删除旧备份
- ✅ **详细日志**: 记录所有备份操作的详细日志
- ✅ **安全恢复**: 恢复前自动创建安全备份

## 文件说明

- `backup_db.py` - 主备份脚本
- `setup_backup_task.bat` - Windows批处理脚本（设置计划任务）
- `setup_backup_task.ps1` - PowerShell脚本（设置计划任务）
- `backups/` - 备份文件存储目录
- `logs/` - 日志文件目录

## 使用方法

### 1. 手动备份

```bash
# 创建备份
python backup_db.py backup

# 列出所有备份
python backup_db.py list

# 恢复备份
python backup_db.py restore pricing_system_backup_20240807_143022.db
```

### 2. 设置自动备份

#### 方法一：使用PowerShell脚本（推荐）

1. 以管理员身份运行PowerShell
2. 执行以下命令：

```powershell
# 设置执行策略（如果需要）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 运行设置脚本
.\setup_backup_task.ps1
```

#### 方法二：使用批处理脚本

1. 以管理员身份运行命令提示符
2. 执行以下命令：

```cmd
setup_backup_task.bat
```

#### 方法三：手动创建计划任务

1. 打开"任务计划程序"
2. 创建基本任务
3. 设置触发器为"每天"
4. 设置操作为运行程序：`python backup_db.py`

### 3. 管理计划任务

```powershell
# 查看任务状态
Get-ScheduledTask -TaskName "LogisticsDBBackup"

# 立即执行任务
Start-ScheduledTask -TaskName "LogisticsDBBackup"

# 删除任务
Unregister-ScheduledTask -TaskName "LogisticsDBBackup" -Confirm:$false
```

## 备份文件命名规则

备份文件按以下格式命名：
```
pricing_system_backup_YYYYMMDD_HHMMSS.db
```

例如：`pricing_system_backup_20240807_143022.db`

## 备份内容

每次备份会记录：
- 数据库表结构
- 物流规则数量
- 产品数量
- 用户数量
- 文件大小验证

## 恢复数据

如果需要恢复数据：

1. 查看可用备份：
   ```bash
   python backup_db.py list
   ```

2. 选择要恢复的备份文件

3. 执行恢复：
   ```bash
   python backup_db.py restore pricing_system_backup_20240807_143022.db
   ```

**注意**: 恢复前会自动创建当前数据库的安全备份

## 日志文件

备份日志保存在 `logs/backup.log` 文件中，包含：
- 备份时间
- 数据库验证结果
- 备份文件大小
- 错误信息（如果有）

## 故障排除

### 常见问题

1. **权限不足**
   - 确保以管理员身份运行设置脚本
   - 检查文件夹写入权限

2. **Python路径问题**
   - 确保Python在系统PATH中
   - 或者修改脚本中的Python路径

3. **数据库被占用**
   - 确保应用程序已关闭
   - 或者使用数据库锁定机制

### 手动清理

如果需要手动清理备份文件：

```bash
# 删除所有备份文件
rm -rf backups/*

# 删除日志文件
rm -rf logs/*
```

## 安全建议

1. **定期检查备份**: 确保备份文件正常创建
2. **异地备份**: 考虑将备份文件复制到其他位置
3. **测试恢复**: 定期测试恢复功能
4. **监控日志**: 关注备份日志中的错误信息

## 联系支持

如果遇到问题，请检查：
1. 日志文件中的错误信息
2. 系统权限设置
3. Python环境配置
