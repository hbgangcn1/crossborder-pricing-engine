#!/usr/bin/env python3
"""
数据库备份工具
自动备份pricing_system.db数据库文件
"""


import shutil
import sqlite3
import datetime
import logging
from pathlib import Path


def setup_logging():
    """设置日志"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "backup.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def get_backup_dir():
    """获取备份目录"""
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    return backup_dir


def create_backup():
    """创建数据库备份"""
    logger = setup_logging()
    
    try:
        # 源数据库文件
        db_path = Path("pricing_system.db")
        if not db_path.exists():
            logger.error("数据库文件不存在: pricing_system.db")
            return False
        
        # 备份目录
        backup_dir = get_backup_dir()
        
        # 生成备份文件名（包含时间戳）
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"pricing_system_backup_{timestamp}.db"
        backup_path = backup_dir / backup_filename
        
        # 验证源数据库完整性
        logger.info("验证数据库完整性...")
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            # 检查表结构
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in c.fetchall()]
            logger.info(f"发现表: {tables}")
            
            # 检查数据量
            if 'logistics' in tables:
                c.execute("SELECT COUNT(*) FROM logistics")
                logistics_count = c.fetchone()[0]
                logger.info(f"物流规则数量: {logistics_count}")
            
            if 'products' in tables:
                c.execute("SELECT COUNT(*) FROM products")
                products_count = c.fetchone()[0]
                logger.info(f"产品数量: {products_count}")
            
            if 'users' in tables:
                c.execute("SELECT COUNT(*) FROM users")
                users_count = c.fetchone()[0]
                logger.info(f"用户数量: {users_count}")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"数据库验证失败: {e}")
            return False
        
        # 创建备份
        logger.info(f"开始备份数据库到: {backup_path}")
        shutil.copy2(db_path, backup_path)
        
        # 验证备份文件
        if backup_path.exists():
            backup_size = backup_path.stat().st_size
            original_size = db_path.stat().st_size
            
            logger.info(f"备份完成!")
            logger.info(f"原始文件大小: {original_size:,} 字节")
            logger.info(f"备份文件大小: {backup_size:,} 字节")
            
            if backup_size == original_size:
                logger.info("备份文件大小验证通过")
            else:
                logger.warning("备份文件大小与原始文件不匹配")
            
            # 清理旧备份（保留最近7天）
            cleanup_old_backups(backup_dir, logger)
            
            return True
        else:
            logger.error("备份文件创建失败")
            return False
            
    except Exception as e:
        logger.error(f"备份过程中发生错误: {e}")
        return False


def cleanup_old_backups(backup_dir, logger):
    """清理旧备份文件（保留最近7天）"""
    try:
        # 获取所有备份文件
        backup_files = list(backup_dir.glob("pricing_system_backup_*.db"))
        
        if len(backup_files) <= 7:
            logger.info(f"当前备份文件数量: {len(backup_files)}，无需清理")
            return
        
        # 按修改时间排序
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # 删除超过7天的备份
        files_to_delete = backup_files[7:]
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                logger.info(f"删除旧备份文件: {file_path.name}")
            except Exception as e:
                logger.error(f"删除文件失败 {file_path.name}: {e}")
        
        logger.info(f"清理完成，保留 {len(backup_files) - len(files_to_delete)} 个备份文件")
        
    except Exception as e:
        logger.error(f"清理旧备份时发生错误: {e}")


def restore_backup(backup_filename):
    """从备份文件恢复数据库"""
    logger = setup_logging()
    
    try:
        backup_dir = get_backup_dir()
        backup_path = backup_dir / backup_filename
        
        if not backup_path.exists():
            logger.error(f"备份文件不存在: {backup_filename}")
            return False
        
        # 创建当前数据库的备份（以防万一）
        current_db = Path("pricing_system.db")
        if current_db.exists():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup = backup_dir / f"pre_restore_backup_{timestamp}.db"
            shutil.copy2(current_db, safety_backup)
            logger.info(f"创建恢复前安全备份: {safety_backup.name}")
        
        # 恢复数据库
        logger.info(f"开始恢复数据库从: {backup_filename}")
        shutil.copy2(backup_path, current_db)
        
        logger.info("数据库恢复完成")
        return True
        
    except Exception as e:
        logger.error(f"恢复过程中发生错误: {e}")
        return False


def list_backups():
    """列出所有备份文件"""
    logger = setup_logging()
    
    try:
        backup_dir = get_backup_dir()
        backup_files = list(backup_dir.glob("pricing_system_backup_*.db"))
        
        if not backup_files:
            logger.info("没有找到备份文件")
            return
        
        logger.info("可用的备份文件:")
        for file_path in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True):
            stat = file_path.stat()
            size = stat.st_size
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
            logger.info(f"  {file_path.name} - {size:,} 字节 - {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            
    except Exception as e:
        logger.error(f"列出备份文件时发生错误: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "backup":
            success = create_backup()
            sys.exit(0 if success else 1)
        elif command == "list":
            list_backups()
        elif command == "restore" and len(sys.argv) > 2:
            backup_file = sys.argv[2]
            success = restore_backup(backup_file)
            sys.exit(0 if success else 1)
        else:
            print("用法:")
            print("  python backup_db.py backup     # 创建备份")
            print("  python backup_db.py list       # 列出备份")
            print("  python backup_db.py restore <filename>  # 恢复备份")
    else:
        # 默认执行备份
        success = create_backup()
        sys.exit(0 if success else 1)
