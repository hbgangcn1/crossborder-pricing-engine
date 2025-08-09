#!/usr/bin/env python3
"""
测试运行器 - 用于运行物流定价系统的各种测试
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n🔍 {description}")
    print("-" * 50)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 成功")
            if result.stdout:
                print(result.stdout)
        else:
            print("❌ 失败")
            if result.stderr:
                print(result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 执行错误: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='运行物流定价系统测试')
    parser.add_argument('--unit', action='store_true', help='运行单元测试')
    parser.add_argument('--integration', action='store_true', help='运行集成测试')
    parser.add_argument('--security', action='store_true', help='运行安全测试')
    parser.add_argument('--performance', action='store_true', help='运行性能测试')
    parser.add_argument('--comprehensive', action='store_true', help='运行综合测试')
    parser.add_argument('--coverage', action='store_true', help='生成覆盖率报告')
    parser.add_argument('--report', action='store_true', help='生成HTML报告')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 如果没有指定特定测试，运行所有测试
    if not any([args.unit, args.integration, args.security, args.performance, args.comprehensive]):
        args.unit = args.integration = args.security = args.performance = args.comprehensive = True
    
    print("🚀 物流定价系统测试套件")
    print("=" * 50)
    
    # 检查测试依赖
    try:
        import pytest
        print("✅ pytest 已安装")
    except ImportError:
        print("❌ pytest 未安装，请运行: pip install -r requirements_test.txt")
        return 1
    
    success_count = 0
    total_count = 0
    
    # 基础测试文件
    test_files = [
        "test_exchange_service.py",
        "test_db_utils.py", 
        "test_backup_db.py"
    ]
    
    if args.unit:
        total_count += 1
        print(f"\n📋 运行单元测试...")
        cmd = f"python -m pytest {' '.join(test_files)} -v"
        if args.verbose:
            cmd += " -s"
        if run_command(cmd, "单元测试"):
            success_count += 1
    
    if args.coverage:
        total_count += 1
        print(f"\n📊 生成覆盖率报告...")
        cmd = f"python -m pytest {' '.join(test_files)} --cov=. --cov-report=html --cov-report=term"
        if run_command(cmd, "覆盖率测试"):
            success_count += 1
            print("📁 覆盖率报告已生成到: htmlcov/index.html")
    
    if args.report:
        total_count += 1
        print(f"\n📄 生成HTML测试报告...")
        cmd = f"python -m pytest {' '.join(test_files)} --html=test_report.html --self-contained-html"
        if run_command(cmd, "HTML报告生成"):
            success_count += 1
            print("📁 测试报告已生成到: test_report.html")
    
    # 显示总结
    print("\n" + "=" * 50)
    print(f"📈 测试完成: {success_count}/{total_count} 成功")
    
    if success_count == total_count:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查日志")
        return 1

if __name__ == "__main__":
    sys.exit(main())