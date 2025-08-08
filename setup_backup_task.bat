@echo off
echo 设置数据库自动备份计划任务...

REM 获取当前目录的绝对路径
set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=python"
set "BACKUP_SCRIPT=%SCRIPT_DIR%backup_db.py"

REM 创建计划任务（每天凌晨2点执行备份）
schtasks /create /tn "LogisticsDBBackup" /tr "%PYTHON_PATH% %BACKUP_SCRIPT%" /sc daily /st 02:00 /f

if %ERRORLEVEL% EQU 0 (
    echo 计划任务创建成功！
    echo 任务名称: LogisticsDBBackup
    echo 执行时间: 每天凌晨2:00
    echo 执行命令: %PYTHON_PATH% %BACKUP_SCRIPT%
    echo.
    echo 你可以通过以下命令管理任务:
    echo   schtasks /query /tn "LogisticsDBBackup"    # 查看任务状态
    echo   schtasks /delete /tn "LogisticsDBBackup"   # 删除任务
) else (
    echo 计划任务创建失败，请以管理员身份运行此脚本
)

pause
