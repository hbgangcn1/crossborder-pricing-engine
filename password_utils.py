"""
密码强度验证工具
"""

import re
from typing import Dict, Any, Union


def validate_password_strength(password: Any) -> Dict[str, Any]:
    """
    验证密码强度

    Args:
        password: 要验证的密码

    Returns:
        包含验证结果的字典
    """
    result = {'is_valid': True, 'errors': [], 'score': 0}

    # 处理 None
    if password is None:
        result['errors'].append('密码不能为空')
        result['is_valid'] = False
        return result

    # 处理非字符串输入
    if not isinstance(password, str):
        result['errors'].append('密码必须是字符串类型')
        result['is_valid'] = False
        return result

    # 长度检查
    if len(password) < 13:
        result['errors'].append('密码长度必须至少13位')
    else:
        result['score'] += 1

    # 大写字母
    if not re.search(r'[A-Z]', password):
        result['errors'].append('密码必须包含大写字母')
    else:
        result['score'] += 1

    # 小写字母
    if not re.search(r'[a-z]', password):
        result['errors'].append('密码必须包含小写字母')
    else:
        result['score'] += 1

    # 数字
    if not re.search(r'\d', password):
        result['errors'].append('密码必须包含数字')
    else:
        result['score'] += 1

    # 特殊字符
    special_chars = r'~!@#$%^&*+-/.,\{}[]();:?<>"\'_`'
    if not re.search(f'[{re.escape(special_chars)}]', password):
        result['errors'].append('密码必须包含特殊字符')
    else:
        result['score'] += 1

    if result['errors']:
        result['is_valid'] = False

    return result


def get_password_requirements_text() -> str:
    """获取密码要求文本"""
    return (
        "密码必须满足以下要求：\n"
        "• 至少13位长度\n"
        "• 包含大写字母\n"
        "• 包含小写字母\n"
        "• 包含数字\n"
        "• 包含特殊字符 (~!@#$%^&*+-/.,\\{}[]();:?<>\"'_`)"
    )


def get_password_strength_color(score: Union[int, float]) -> str:
    """
    根据密码强度分数返回颜色

    Args:
        score: 密码强度分数 (0-5)

    Returns:
        颜色字符串
    """
    if score <= 1:
        return "red"
    elif score <= 2:
        return "orange"
    elif score <= 3:
        return "yellow"
    elif score <= 4:
        return "lightgreen"
    else:
        return "green"


def check_password_strength(password: Any) -> Dict[str, Any]:
    """
    检查密码强度（兼容性函数）

    Args:
        password: 要检查的密码

    Returns:
        包含验证结果的字典
    """
    return validate_password_strength(password)
