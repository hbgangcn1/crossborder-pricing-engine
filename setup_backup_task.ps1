# 数据库自动备份计划任务设置脚本
# 需要以管理员身份运行

param(
    [string]$Time = "02:00",
    [string]$TaskName = "LogisticsDBBackup"
)

Write-Host "设置数据库自动备份计划任务..." -ForegroundColor Green

# 获取当前目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = "python"
$BackupScript = Join-Path $ScriptDir "backup_db.py"

# 检查备份脚本是否存在
if (-not (Test-Path $BackupScript)) {
    Write-Host "错误: 找不到备份脚本 $BackupScript" -ForegroundColor Red
    exit 1
}

# 创建任务动作
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument $BackupScript -WorkingDirectory $ScriptDir

# 创建触发器（每天执行）
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time

# 创建任务设置
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# 创建任务
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "物流系统数据库自动备份" -Force
    
    Write-Host "计划任务创建成功！" -ForegroundColor Green
    Write-Host "任务名称: $TaskName" -ForegroundColor Yellow
    Write-Host "执行时间: 每天 $Time" -ForegroundColor Yellow
    Write-Host "执行命令: $PythonPath $BackupScript" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "管理命令:" -ForegroundColor Cyan
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName'    # 查看任务状态" -ForegroundColor White
    Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:$false    # 删除任务" -ForegroundColor White
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'    # 立即执行任务" -ForegroundColor White
    
} catch {
    Write-Host "计划任务创建失败: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "请确保以管理员身份运行此脚本" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "按任意键继续..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
