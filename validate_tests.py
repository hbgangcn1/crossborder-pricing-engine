#!/usr/bin/env python3
"""
测试套件验证脚本

这个脚本用于验证测试套件的可靠性和完整性。
它会运行测试并检查是否覆盖了关键功能。
"""

import os
import sys
import subprocess
import importlib
import inspect
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_module_exists(module_name):
    """检查模块是否存在"""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def get_module_functions(module_name):
    """获取模块中的所有函数"""
    try:
        module = importlib.import_module(module_name)
        functions = []
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and not name.startswith('_'):
                functions.append(name)
        return functions
    except ImportError:
        return []


def check_test_coverage():
    """检查测试覆盖率"""
    print("🔍 检查测试覆盖率...")

    # 检查主要模块是否有对应的测试
    main_modules = [
        'ui_pricing_simple',
        'ui_user',
        'ui_products',
        'ui_logistics',
        'logic',
        'db_utils'
    ]

    test_modules = [
        'test_ui_pricing_simple',
        'test_ui_modules',
        'test_logic',
        'test_db_utils'
    ]

    missing_tests = []
    for module in main_modules:
        if not any(module.replace('ui_', 'test_ui_') in test_mod or
                   module in test_mod for test_mod in test_modules):
            missing_tests.append(module)

    if missing_tests:
        print(f"❌ 缺少以下模块的测试: {missing_tests}")
        return False
    else:
        print("✅ 所有主要模块都有对应的测试")
        return True


def run_specific_tests():
    """运行特定的关键测试"""
    print("\n🧪 运行关键测试...")

    test_commands = [
        ["python", "-m", "pytest", "tests/test_ui_pricing_simple.py", "-v"],
        ["python", "-m", "pytest", "tests/test_logic.py", "-v"],
        ["python", "-m", "pytest", "tests/test_db_utils.py", "-v"]
    ]

    all_passed = True

    for cmd in test_commands:
        print(f"\n运行: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=project_root)
            if result.returncode == 0:
                print("✅ 测试通过")
            else:
                print("❌ 测试失败")
                print("错误输出:")
                print(result.stderr)
                all_passed = False
        except Exception as e:
            print(f"❌ 运行测试时出错: {e}")
            all_passed = False

    return all_passed


def check_dataframe_operations():
    """检查DataFrame操作的正确性"""
    print("\n📊 检查DataFrame操作...")

    try:
        import pandas as pd

        # 创建测试数据
        data = {
            'type': [
                'land', 'land', 'air', 'air'], 'delivery_method': [
                'pickup_point', 'home_delivery', 'pickup_point', 'home_delivery'], 'name': [
                '陆运A', '陆运B', '空运A', '空运B'], 'time_efficiency': [
                    7, 8, 3, 4]}
        df = pd.DataFrame(data)

        # 测试过滤操作
        land_logistics = df[df['type'] == 'land'].copy()
        air_logistics = df[df['type'] == 'air'].copy()

        # 测试取货点过滤
        pickup_land = land_logistics[land_logistics['delivery_method']
                                     == 'pickup_point'].copy()
        home_land = land_logistics[land_logistics['delivery_method']
                                   == 'home_delivery'].copy()

        # 验证结果
        assert isinstance(land_logistics, pd.DataFrame)
        assert isinstance(air_logistics, pd.DataFrame)
        assert isinstance(pickup_land, pd.DataFrame)
        assert isinstance(home_land, pd.DataFrame)

        assert len(land_logistics) == 2
        assert len(air_logistics) == 2
        assert len(pickup_land) == 1
        assert len(home_land) == 1

        assert 'iloc' in dir(pickup_land)
        assert 'empty' in dir(pickup_land)

        print("✅ DataFrame操作测试通过")
        return True

    except Exception as e:
        print(f"❌ DataFrame操作测试失败: {e}")
        return False


def check_imports():
    """检查关键模块的导入"""
    print("\n📦 检查模块导入...")

    required_modules = [
        'ui_pricing_simple',
        'logic',
        'db_utils',
        'exchange_service'
    ]

    all_imported = True
    for module in required_modules:
        if check_module_exists(module):
            print(f"✅ {module} 导入成功")
        else:
            print(f"❌ {module} 导入失败")
            all_imported = False

    return all_imported


def check_function_signatures():
    """检查关键函数的签名"""
    print("\n🔧 检查函数签名...")

    try:
        from ui_pricing_simple import display_logistics_result, pricing_calculator_page

        # 检查display_logistics_result函数
        sig = inspect.signature(display_logistics_result)
        params = list(sig.parameters.keys())
        expected_params = ['logistics_item', 'product', 'current_rate']

        if params == expected_params:
            print("✅ display_logistics_result 函数签名正确")
        else:
            print(
                f"❌ display_logistics_result 函数签名错误: 期望 {expected_params}, 实际 {params}")
            return False

        # 检查pricing_calculator_page函数
        sig = inspect.signature(pricing_calculator_page)
        params = list(sig.parameters.keys())
        expected_params = []

        if params == expected_params:
            print("✅ pricing_calculator_page 函数签名正确")
        else:
            print(
                f"❌ pricing_calculator_page 函数签名错误: 期望 {expected_params}, 实际 {params}")
            return False

        return True

    except Exception as e:
        print(f"❌ 检查函数签名时出错: {e}")
        return False


def main():
    """主函数"""
    print("🚀 开始验证测试套件...")

    checks = [
        ("模块导入", check_imports),
        ("函数签名", check_function_signatures),
        ("DataFrame操作", check_dataframe_operations),
        ("测试覆盖率", check_test_coverage),
        ("关键测试", run_specific_tests)
    ]

    results = []
    for check_name, check_func in checks:
        print(f"\n{'=' * 50}")
        print(f"检查: {check_name}")
        print('=' * 50)
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"❌ 检查 {check_name} 时出错: {e}")
            results.append((check_name, False))

    # 总结
    print(f"\n{'=' * 50}")
    print("验证结果总结")
    print('=' * 50)

    passed = 0
    total = len(results)

    for check_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{check_name}: {status}")
        if result:
            passed += 1

    print(f"\n总体结果: {passed}/{total} 项检查通过")

    if passed == total:
        print("🎉 所有检查都通过了！测试套件是可靠的。")
        return 0
    else:
        print("⚠️  部分检查失败，建议修复相关问题。")
        return 1


if __name__ == "__main__":
    exit(main())
