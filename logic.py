# logic.py

import math
from exchange_service import ExchangeRateService


def calculate_logistic_cost(logistic, product, debug=False):
    """计算物流成本"""
    debug_info = []
    # 计算体积重量
    length_cm = product.get("length_cm", 0)
    width_cm = product.get("width_cm", 0)
    height_cm = product.get("height_cm", 0)
    volume_mode = logistic.get("volume_mode", "none")
    volume_coefficient = logistic.get("volume_coefficient", 5000)
    debug_info.append(f"体积重量模式: {volume_mode}, 系数: {volume_coefficient}")
    if volume_mode == "max_actual_vs_volume":
        volume_weight = (length_cm * width_cm * height_cm) / volume_coefficient
        actual_weight = product.get("weight_g", 0) / 1000  # 转换为千克
        calculated_weight = max(actual_weight, volume_weight) * 1000  # 转换回克
        debug_info.append(
            f"实际重量: {actual_weight * 1000:.2f}g, "
            f"体积重量: {volume_weight * 1000:.2f}g, "
            f"计费重量: {calculated_weight:.2f}g"
        )
    else:
        calculated_weight = product.get("weight_g", 0)
        debug_info.append(f"实际重量: {calculated_weight}g（未启用体积重量）")
    # 基础限制
    w = calculated_weight
    min_w = logistic.get("min_weight", 0)
    max_w = logistic.get("max_weight", 10**9)
    debug_info.append(f"重量限制: {min_w}g ~ {max_w}g, 当前: {w}g")
    if w < min_w or w > max_w:
        debug_info.append("不满足重量限制，返回 None")
        return (None, debug_info) if debug else None
    try:
        sides = [
            product.get("length_cm", 0),
            product.get("width_cm", 0),
            product.get("height_cm", 0),
        ]
        debug_info.append(f"三边: {sides}, 三边和: {sum(sides)}, 最长边: {max(sides)}")
        # 判断是标准包装还是圆柱形包装
        has_cylinder_limits = (
            logistic.get("max_cylinder_sum", 0) > 0
            or logistic.get("max_cylinder_length", 0) > 0
            or logistic.get("min_cylinder_length", 0) > 0
        )
        if has_cylinder_limits:
            # 圆柱形包装限制
            cylinder_diameter = product.get("cylinder_diameter", 0)
            cylinder_length = product.get("length_cm", 0)
            cylinder_sum = 2 * cylinder_diameter + cylinder_length
            debug_info.append(
                f"圆柱形包装: 直径={cylinder_diameter}cm, "
                f"长度={cylinder_length}cm, "
                f"2倍直径+长度={cylinder_sum}cm"
            )
            max_cylinder_sum = logistic.get("max_cylinder_sum", 0)
            if 0 < max_cylinder_sum < cylinder_sum:
                debug_info.append(
                    (
                        "2倍直径与长度之和 "
                        f"{cylinder_sum}cm 超限 {max_cylinder_sum}cm，"
                        "返回 None"
                    )
                )
                return (None, debug_info) if debug else None
            max_cylinder_length = logistic.get("max_cylinder_length", 0)
            if 0 < max_cylinder_length < cylinder_length:
                debug_info.append(
                    (
                        "圆柱长度 "
                        f"{cylinder_length}cm 超限 {max_cylinder_length}cm，"
                        "返回 None"
                    )
                )
                return (None, debug_info) if debug else None
            min_cyl = logistic.get("min_cylinder_length", 0)
            if min_cyl > 0 and cylinder_length < min_cyl:
                debug_info.append(
                    (
                        "圆柱长度 "
                        f"{cylinder_length}cm 低于下限 {min_cyl}cm，"
                        "返回 None"
                    )
                )
                return (None, debug_info) if debug else None
        else:
            # 标准包装限制
            if sum(sides) > logistic.get("max_sum_of_sides", 10**9):
                debug_info.append("三边和超限，返回 None")
                return (None, debug_info) if debug else None
            if max(sides) > logistic.get("max_longest_side", 10**9):
                debug_info.append("最长边超限，返回 None")
                return (None, debug_info) if debug else None
            # 第二边长上限检查
            max_second_side = logistic.get("max_second_side", 0)
            if max_second_side > 0:
                sorted_sides = sorted(sides, reverse=True)
                second_side = sorted_sides[1] if len(sorted_sides) > 1 else 0
                debug_info.append(
                    f"第二边长: {second_side}cm, 限制: {max_second_side}cm"
                )
                if 0 < max_second_side < second_side:
                    debug_info.append(
                        f"第二边长 {second_side}cm 超限 {max_second_side}cm，返回 None"
                    )
                    return (None, debug_info) if debug else None
            # 长度下限检查
            min_len = logistic.get("min_length", 0)
            if min_len > 0:
                length = product.get("length_cm", 0)
                debug_info.append(f"长度: {length}cm, 下限: {min_len}cm")
                if length < min_len:
                    debug_info.append(
                        f"长度 {length}cm 低于下限 {min_len}cm，返回 None"
                    )
                    return (None, debug_info) if debug else None
        if product.get("has_battery") and not logistic.get("allow_battery"):
            debug_info.append("产品含电池但物流不允许，返回 None")
            return (None, debug_info) if debug else None
        if product.get("has_flammable") and not logistic.get(
                "allow_flammable"):
            debug_info.append("产品含易燃液体但物流不允许，返回 None")
            return (None, debug_info) if debug else None
        # 电池容量 & MSDS
        if product.get("has_battery"):
            limit_wh = logistic.get("battery_capacity_limit_wh", 0)
            if limit_wh > 0:
                wh = product.get("battery_capacity_wh", 0)
                if wh == 0:
                    mah = product.get("battery_capacity_mah", 0)
                    v = product.get("battery_voltage", 0)
                    wh = mah * v / 1000.0
                debug_info.append(f"电池容量: {wh}Wh, 限制: {limit_wh}Wh")
                if 0 < limit_wh < wh:
                    debug_info.append("电池容量超限，返回 None")
                    return (None, debug_info) if debug else None
            if logistic.get("require_msds") and not product.get("has_msds"):
                debug_info.append("要求 MSDS 但产品未提供，返回 None")
                return (None, debug_info) if debug else None
    except Exception as e:
        debug_info.append(f"计算物流成本时出错: {str(e)}")
        if debug:
            return None, debug_info
        else:
            return None
    # 重量计费
    w = product.get("weight_g", 0)
    fee_mode = logistic.get("fee_mode", "base_plus_continue")
    continue_unit = int(logistic.get("continue_unit", 100))
    continue_fee = logistic.get("continue_fee", 0)
    debug_info.append(
        f"计费方式: {fee_mode}, 续重单位: {continue_unit}g, 续重费用: {continue_fee}"
    )
    if fee_mode == "base_plus_continue":
        units = math.ceil(w / continue_unit)
        cost = logistic.get("base_fee", 0) + continue_fee * units
        debug_info.append(
            f"基础费用: {logistic.get('base_fee', 0)}, "
            f"单位数: {units}, 运费: {cost}"
        )
    else:  # first_plus_continue
        first_weight = logistic.get("first_weight_g", 0)
        first_fee = logistic.get("first_fee", 0)
        if w <= first_weight:
            cost = first_fee
            debug_info.append(f"首重费用: {first_fee}，在首重范围内")
        else:
            extra_units = math.ceil((w - first_weight) / continue_unit)
            cost = first_fee + continue_fee * extra_units
            debug_info.append(
                f"首重费用: {first_fee}，超出部分单位数: {extra_units}，总运费: {cost}"
            )
    # 限价判断（人民币→卢布）
    try:
        rate = ExchangeRateService().get_exchange_rate()  # 1 CNY = x RUB
        unit_price = float(product.get("unit_price", 0))
        labeling_fee = float(product.get("labeling_fee", 0))
        shipping_fee = float(product.get("shipping_fee", 0))
        total_cny = unit_price + labeling_fee + shipping_fee + 15 * rate + cost
        rough_cny = (
            total_cny
            * (1 + product.get("target_profit_margin", 0))
            / (
                (1 - product.get("promotion_discount", 0))
                * (1 - product.get("commission_rate", 0))
                * (1 - product.get("withdrawal_fee_rate", 0))
                * (1 - product.get("payment_processing_fee", 0))
            )
        )
        rough_rub = rough_cny / rate

        # 获取价格限制和货币类型
        limit_value = logistic.get("price_limit_rub") or 0
        min_value = logistic.get("price_min_rub") or 0
        limit_currency = logistic.get("price_limit_currency", "RUB")
        min_currency = logistic.get("price_min_currency", "RUB")

        # 根据货币类型进行价格比较
        from exchange_service import get_usd_rate
        usd_rate = get_usd_rate()

        if limit_currency == "USD" and limit_value > 0:
            # 美元限价：将估算售价转换为美元进行比较
            rough_usd = rough_cny / usd_rate
            debug_info.append(
                f"限价判断: 估算售价 {rough_usd:.2f} USD, "
                f"上限 {limit_value:.2f} USD"
            )
            if rough_usd > limit_value:
                debug_info.append("超价格上限，返回 None")
                return (None, debug_info) if debug else None
        elif limit_value > 0:
            # 卢布限价：直接比较卢布价格
            debug_info.append(
                f"限价判断: 估算售价 {rough_rub:.2f} RUB, "
                f"上限 {limit_value:.2f} RUB"
            )
            if rough_rub > limit_value:
                debug_info.append("超价格上限，返回 None")
                return (None, debug_info) if debug else None

        if min_currency == "USD" and min_value > 0:
            # 美元下限：将估算售价转换为美元进行比较
            rough_usd = rough_cny / usd_rate
            debug_info.append(f"下限 {min_value:.2f} USD")
            if rough_usd < min_value:
                debug_info.append("低于价格下限，返回 None")
                return (None, debug_info) if debug else None
        elif min_value > 0:
            # 卢布下限：直接比较卢布价格
            debug_info.append(f"下限 {min_value:.2f} RUB")
            if rough_rub < min_value:
                debug_info.append("低于价格下限，返回 None")
                return (None, debug_info) if debug else None
    except Exception as e:
        debug_info.append(f"限价判断出错: {e}")
        if debug:
            return None, debug_info
        else:
            return None
    debug_info.append(f"最终运费: {cost}")
    return (cost, debug_info) if debug else cost


def calculate_pricing(product, land_logistics, air_logistics,
                      priority="低价优先", price_limit=0.0,
                      price_limit_currency="卢布", price_min=0.0,
                      price_min_currency="卢布"):
    """计算定价"""
    from functools import lru_cache
    from exchange_service import get_usd_rate

    # 1. 基础数据
    unit_price = float(product["unit_price"])
    labeling_fee = float(product["labeling_fee"])
    shipping_fee = float(product["shipping_fee"])
    rate = ExchangeRateService().get_exchange_rate()
    usd_rate = get_usd_rate()

    # 货币转换（如果没有传入价格限制，则使用默认值）
    if price_limit_currency == "卢布":
        price_limit_cny = price_limit / rate if price_limit > 0 else 0
    else:  # 美元
        price_limit_cny = price_limit * usd_rate if price_limit > 0 else 0

    if price_min_currency == "卢布":
        price_min_cny = price_min / rate if price_min > 0 else 0
    else:  # 美元
        price_min_cny = price_min * usd_rate if price_min > 0 else 0

    # 2. 缓存版 calculate_logistic_cost
    @lru_cache(maxsize=256)
    def cached_cost(log_tuple, prod_tuple):
        return calculate_logistic_cost(
            dict(log_tuple), dict(prod_tuple), debug=True)
    # 3. 过滤可用物流
    all_costs_debug = []

    def _cost_and_filter(logistics):
        res = []
        for log in logistics:
            cost, debug_info = cached_cost(
                tuple(log.items()), tuple(product.items()))
            all_costs_debug.append({
                "logistic": log,
                "cost": cost,
                "debug": debug_info
            })
            if cost is None:
                continue

            # 粗略估算价格
            rough = (
                (unit_price + labeling_fee + shipping_fee + 15 * rate + cost)
                * (1 + product["target_profit_margin"])
                / (
                    (1 - product["promotion_discount"])
                    * (1 - product["commission_rate"])
                    * (1 - product["withdrawal_fee_rate"])
                    * (1 - product["payment_processing_fee"])
                )
            )

            # 价格限制检查
            limit = log.get("price_limit") or 0
            min_limit = log.get("price_min_rub") or 0

            # 使用页面设置的价格限制（优先级更高）
            if price_limit_cny > 0:
                limit = price_limit_cny
            if price_min_cny > 0:
                min_limit = price_min_cny

            # 检查价格上限和下限
            if 0 < limit < rough:
                continue
            if min_limit > 0 and rough < min_limit:
                continue

            res.append((log, cost))
        return res
    land_candidates = _cost_and_filter(land_logistics)
    air_candidates = _cost_and_filter(air_logistics)

    # 4. 按优先级选择最优
    def select_best_by_priority(candidates, priority_type):
        if not candidates:
            return None, None

        if priority_type == "速度优先":
            # 按优先级组和平均时效排序
            def speed_key(candidate):
                log = candidate[0]
                priority_group = log.get("priority_group", "D")
                min_days = log.get("min_days", 0)
                max_days = log.get("max_days", 0)
                avg_time = (min_days + max_days) / 2
                # 优先级组：A=0, B=1, C=2, D=3
                group_priority = (
                    {"A": 0, "B": 1, "C": 2, "D": 3}.get(priority_group, 3)
                )
                return group_priority, avg_time

            return min(candidates, key=speed_key)
        else:  # 低价优先
            # 按价格排序，价格相同时按优先级组和平均时效排序
            def price_key(candidate):
                log = candidate[0]
                cost = candidate[1]
                priority_group = log.get("priority_group", "D")
                min_days = log.get("min_days", 0)
                max_days = log.get("max_days", 0)
                avg_time = (min_days + max_days) / 2
                group_priority = (
                    {"A": 0, "B": 1, "C": 2, "D": 3}.get(priority_group, 3)
                )
                return cost, group_priority, avg_time

            return min(candidates, key=price_key)

    land_best = select_best_by_priority(land_candidates, priority)
    air_best = select_best_by_priority(air_candidates, priority)

    # 5. 最终价格
    def _final_price(cost, debug_list=None):
        total_cost = (
            unit_price
            + labeling_fee
            + shipping_fee
            + cost
            + 15 * rate
        )
        denominator = (
            (1 - product["promotion_discount"])
            * (1 - product["commission_rate"])
            * (1 - product["withdrawal_fee_rate"])
            * (1 - product["payment_processing_fee"])
        )
        price = round(
            total_cost * (1 + product["target_profit_margin"]) / denominator, 2
        )
        if debug_list is not None:
            debug_list.append(
                "定价公式: (("
                f"{total_cost:.2f}) * (1 + "
                f"{product['target_profit_margin']})"
                ") / "
                f"{denominator:.4f} = "
                f"{price:.2f}"
            )

            # 添加价格限制调试信息（仅当有设置价格限制时显示）
            if price_limit_cny > 0:
                currency_display = (
                    "USD" if price_limit_currency == "美元" else "RUB"
                )
                debug_list.append(
                    f"价格上限: {price_limit:.2f} {currency_display} "
                    f"(约 {price_limit_cny:.2f} CNY)"
                )
            if price_min_cny > 0:
                currency_display = (
                    "USD" if price_min_currency == "美元" else "RUB"
                )
                debug_list.append(
                    f"价格下限: {price_min:.2f} {currency_display} "
                    f"(约 {price_min_cny:.2f} CNY)"
                )
        return price
    land_debug = []
    air_debug = []

    # 一次性拆包，避免重复判断，彻底消除PyCharm警告
    land_log, land_cost = (
        land_best if land_best[0] is not None else (None, None)
    )
    air_log, air_cost = (
        air_best if air_best[0] is not None else (None, None)
    )

    if land_log:
        land_price = _final_price(land_cost, land_debug)
    else:
        land_price = None
    air_price = _final_price(air_cost, air_debug) if air_log else None

    return (
        land_price,
        air_price,
        land_cost,
        air_cost,
        land_log["name"] if land_log else None,
        air_log["name"] if air_log else None,
        all_costs_debug,  # 新增：所有物流的运费和调试信息
        land_debug,  # 新增：陆运定价调试信息
        air_debug,  # 新增：空运定价调试信息
    )


def _debug_filter_reason(logistic: dict, product: dict) -> str | None:
    """检查物流被淘汰的原因"""
    # ---------- 1. 重量 ----------
    w = product.get("weight_g", 0)
    min_w = logistic.get("min_weight", 0)
    max_w = logistic.get("max_weight", 10**9)
    if w < min_w:
        return f"重量 {w} g 低于下限 {min_w} g"
    if w > max_w:
        return f"重量 {w} g 高于上限 {max_w} g"
    # ---------- 2. 边长 ----------
    sides = [
        product.get("length_cm", 0),
        product.get("width_cm", 0),
        product.get("height_cm", 0),
    ]
    # 判断是标准包装还是圆柱形包装
    has_cylinder_limits = (
        logistic.get("max_cylinder_sum", 0) > 0
        or logistic.get("max_cylinder_length", 0) > 0
        or logistic.get("min_cylinder_length", 0) > 0
    )
    if has_cylinder_limits:
        # 圆柱形包装限制
        cylinder_diameter = product.get("cylinder_diameter", 0)
        cylinder_length = product.get("length_cm", 0)
        cylinder_sum = 2 * cylinder_diameter + cylinder_length
        max_cylinder_sum = logistic.get("max_cylinder_sum", 0)
        if 0 < max_cylinder_sum < cylinder_sum:
            return f"2倍直径与长度之和 {cylinder_sum} cm 超过限制 {max_cylinder_sum} cm"
        max_cylinder_length = logistic.get("max_cylinder_length", 0)
        if 0 < max_cylinder_length < cylinder_length:
            return f"圆柱长度 {cylinder_length} cm 超过限制 {max_cylinder_length} cm"
        min_cyl = logistic.get("min_cylinder_length", 0)
        if min_cyl > 0 and cylinder_length < min_cyl:
            return f"圆柱长度 {cylinder_length} cm 低于下限 {min_cyl} cm"
    else:
        # 标准包装限制
        max_sum = logistic.get("max_sum_of_sides", 10**9)
        if sum(sides) > max_sum:
            return f"三边之和 {sum(sides)} cm 超过限制 {max_sum} cm"
        max_long = logistic.get("max_longest_side", 10**9)
        if max(sides) > max_long:
            return f"最长边 {max(sides)} cm 超过限制 {max_long} cm"
        # 第二边长上限检查
        max_second_side = logistic.get("max_second_side", 0)
        if max_second_side > 0:
            sorted_sides = sorted(sides, reverse=True)
            second_side = sorted_sides[1] if len(sorted_sides) > 1 else 0
            if 0 < max_second_side < second_side:
                return f"第二边长 {second_side} cm 超过限制 {max_second_side} cm"
        # 长度下限检查
        min_len = logistic.get("min_length", 0)
        if min_len > 0:
            length = product.get("length_cm", 0)
            if length < min_len:
                return f"长度 {length} cm 低于下限 {min_len} cm"
    # 3. 特殊物品
    if product.get("has_battery") and not logistic.get("allow_battery"):
        return "产品含电池但物流不允许电池"
    if product.get("has_flammable") and not logistic.get("allow_flammable"):
        return "产品含易燃液体但物流不允许易燃液体"
    # 4. 电池容量 & MSDS
    if product.get("has_battery"):
        limit_wh = logistic.get("battery_capacity_limit_wh", 0)
        if limit_wh > 0:
            wh = product.get("battery_capacity_wh", 0)
            if wh == 0:
                mah = product.get("battery_capacity_mah", 0)
                v = product.get("battery_voltage", 0)
                wh = mah * v / 1000.0
            if 0 < limit_wh < wh:
                return f"电池容量 {wh} Wh 超过物流限制 {limit_wh} Wh"
        if logistic.get("require_msds") and not product.get("has_msds"):
            return "物流要求 MSDS 但产品未提供"
    # 5. 限价（人民币→卢布）
    try:
        rate = ExchangeRateService().get_exchange_rate()  # 1 CNY = x RUB
        unit_price = float(product.get("unit_price", 0))
        labeling_fee = float(product.get("labeling_fee", 0))
        shipping_fee = float(product.get("shipping_fee", 0))
        # 先计算运费（复用与正式计算完全一致的公式）
        w = product.get("weight_g", 0)
        fee_mode = logistic.get("fee_mode", "base_plus_continue")
        continue_unit = int(logistic.get("continue_unit", 100))
        if fee_mode == "base_plus_continue":
            units = math.ceil(w / continue_unit)
            cost = logistic.get("base_fee", 0) + \
                logistic.get("continue_fee", 0) * units
        else:  # first_plus_continue
            first_w = logistic.get("first_weight_g", 0)
            first_cost = logistic.get("first_fee", 0)
            cost = (
                first_cost
                if w <= first_w
                else first_cost
                + math.ceil((w - first_w) / continue_unit)
                * logistic.get("continue_fee", 0)
            )
        # 估算人民币总成本
        total_cny = unit_price + labeling_fee + shipping_fee + 15 * rate + cost
        # 估算人民币售价
        denominator = (
            (1 - product.get("promotion_discount", 0))
            * (1 - product.get("commission_rate", 0))
            * (1 - product.get("withdrawal_fee_rate", 0))
            * (1 - product.get("payment_processing_fee", 0))
        )
        if denominator == 0:
            return "费率参数异常导致除以 0"
        rough_cny = (
            total_cny
            * (1 + product.get("target_profit_margin", 0))
            / denominator
        )
        rough_rub = rough_cny / rate

        # 获取价格限制和货币类型
        limit_value = logistic.get("price_limit_rub", 0)
        min_value = logistic.get("price_min_rub", 0)
        limit_currency = logistic.get("price_limit_currency", "RUB")
        min_currency = logistic.get("price_min_currency", "RUB")

        # 根据货币类型进行价格比较
        from exchange_service import get_usd_rate
        usd_rate = get_usd_rate()

        if limit_currency == "USD" and limit_value > 0:
            # 美元限价：将估算售价转换为美元进行比较
            rough_usd = rough_cny / usd_rate
            if rough_usd > limit_value:
                return f"估算售价 {rough_usd:.2f} USD 超价格上限 {limit_value} USD"
        elif limit_value > 0:
            # 卢布限价：直接比较卢布价格
            if rough_rub > limit_value:
                return f"估算售价 {rough_rub:.2f} RUB 超价格上限 {limit_value} RUB"

        if min_currency == "USD" and min_value > 0:
            # 美元下限：将估算售价转换为美元进行比较
            rough_usd = rough_cny / usd_rate
            if rough_usd < min_value:
                return f"估算售价 {rough_usd:.2f} USD 低于价格下限 {min_value} USD"
        elif min_value > 0:
            # 卢布下限：直接比较卢布价格
            if rough_rub < min_value:
                return f"估算售价 {rough_rub:.2f} RUB 低于价格下限 {min_value} RUB"
    except Exception as e:
        return f"限价判断异常: {e}"
    # 6. 全部通过
    return None
