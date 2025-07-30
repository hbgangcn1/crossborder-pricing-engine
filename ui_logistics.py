import streamlit as st
import pandas as pd
from db_utils import (
    get_db, current_user_id, calculate_and_update_priority_groups
)
from exchange_service import ExchangeRateService, get_usd_rate


def logistics_page():
    """物流规则页面"""
    conn, c = get_db()
    uid = current_user_id()

    if st.session_state.get("edit_logistic_id"):
        edit_logistic_form()
        return

    # ------------------------------------------------------------------
    # 添加物流规则（展开/收起）
    # ------------------------------------------------------------------
    with st.expander("添加物流规则", expanded=True):
        st.subheader("添加物流规则")
        name = st.text_input("物流名称*", key="add_name")
        logistic_type = st.selectbox("物流类型*", ["陆运", "空运"], key="add_type")
        min_days = st.number_input(
            "最快时效(天)*",
            min_value=1,
            value=10,
            key="add_min_days"
        )
        max_days = st.number_input(
            "最慢时效(天)*",
            min_value=min_days,
            value=30,
            key="add_max_days"
        )

        st.subheader("计费方式")
        fee_mode = st.radio(
            "计费方式",
            ["基础费用+续重费用", "首重费用+续重费用"],
            key="add_fee_mode"
        )
        unit_map = {
            "克": "1",
            "50克": "50",
            "100克": "100",
            "500克": "500",
            "1千克": "1000",
        }
        if fee_mode == "基础费用+续重费用":
            base_fee = st.number_input(
                "基础费用(元)",
                value=0.0,
                key="add_base_fee"
            )
            continue_fee = st.number_input(
                "续重费用(元 / 单位)",
                value=0.0,
                key="add_continue_fee"
            )
            continue_unit = st.selectbox(
                "续重单位",
                list(unit_map.keys()),
                key="add_continue_unit"
            )
            first_fee, first_weight_g = 0.0, 0
        else:
            first_fee = st.number_input(
                "首重费用(元)",
                value=0.0,
                key="add_first_fee"
            )
            first_weight_g = st.number_input(
                "首重重量(克)",
                min_value=0,
                value=0,
                key="add_first_weight"
            )
            continue_fee = st.number_input(
                "续重费用(元 / 单位)",
                value=0.0,
                key="add_continue_fee_alt"
            )
            continue_unit = st.selectbox(
                "续重单位",
                list(unit_map.keys()),
                key="add_continue_unit_alt"
            )
            base_fee = 0.0
        st.subheader("重量限制")
        min_weight = st.number_input(
            "最小重量(g)",
            value=0,
            key="add_min_weight"
        )
        max_weight = st.number_input(
            "最大重量(g)",
            value=0,
            key="add_max_weight"
        )
        st.subheader("包装规定")

        # 标准包装部分
        st.write("**标准包装**")
        max_sum_of_sides = st.number_input(
            "三边之和限制(cm)",
            value=0,
            key="add_max_sum_of_sides"
        )
        max_longest_side = st.number_input(
            "最长边限制(cm)",
            value=0,
            key="add_max_longest_side"
        )
        max_second_side = st.number_input(
            "第二边长上限(cm)",
            value=0,
            help="0表示不限制",
            key="add_max_second_side"
        )
        min_length = st.number_input(
            "长度下限(cm)",
            value=0,
            help="0表示不限制",
            key="add_min_length"
        )

        st.divider()

        # 圆柱形包装部分
        st.write("**圆柱形包装**")
        max_cylinder_sum = st.number_input(
            "2倍直径与长度之和限制(cm)",
            value=0,
            key="add_max_cylinder_sum"
        )
        max_cylinder_length = st.number_input(
            "长度限制(cm)",
            value=0,
            key="add_max_cylinder_length"
        )
        min_cylinder_length = st.number_input(
            "长度下限(cm)",
            value=0,
            help="0表示不限制",
            key="add_min_cylinder_length"
        )

        st.subheader("体积重量计费方式")

        def volume_mode_format(x):
            return {
                "none": "不计算体积重量",
                "max_actual_vs_volume": "取实际重量与体积重量较大者",
                "longest_side": "最长边超过阈值时按体积重量计费",
            }[x]

        volume_mode = st.selectbox(
            "体积重量计费方式",
            ["none", "max_actual_vs_volume", "longest_side"],
            format_func=volume_mode_format,
            key="add_volume_mode"
        )
        longest_side_threshold = 0.0
        volume_coefficient = 0.0
        if volume_mode == "longest_side":
            longest_side_threshold = st.number_input(
                "最长边阈值(cm)",
                min_value=0.0,
                value=0.0,
                key="add_longest_side_threshold"
            )
            volume_coefficient = st.number_input(
                "体积重量系数",
                min_value=1.0,
                value=5000.0,
                key="add_volume_coefficient_longest"
            )
        elif volume_mode == "max_actual_vs_volume":
            volume_coefficient = st.number_input(
                "体积重量系数",
                min_value=1.0,
                value=5000.0,
                key="add_volume_coefficient_max"
            )

        st.subheader("送货方式")
        delivery_method = st.radio(
            "送货方式",
            ["送货上门", "送货到取货点", "未知"],
            horizontal=True,
            key="add_delivery_method"
        )

        st.subheader("价格限制")
        col1, col2 = st.columns(2)
        with col1:
            price_limit = st.number_input(
                "价格上限",
                min_value=0.0,
                value=0.0,
                help=(
                    "物流方给出的最高价格限制"
                ),
                key="add_price_limit"
            )
        with col2:
            price_min = st.number_input(
                "价格下限",
                min_value=0.0,
                value=0.0,
                help=(
                    "物流方给出的最低价格限制，0表示不限制"
                ),
                key="add_price_min"
            )
        price_currency = st.selectbox(
            "货币单位",
            ["卢布", "美元"],
            key="add_price_currency"
        )

        st.subheader("特殊物品限制")
        allow_battery = st.checkbox(
            "允许运输含电池产品",
            key="add_allow_battery"
        )
        battery_capacity_limit_wh = 0.0
        require_msds = False
        if allow_battery:
            battery_capacity_limit_wh = st.number_input(
                "电池容量限制(Wh)",
                min_value=0.0,
                value=0.0,
                step=0.1,
                key="add_battery_capacity_limit"
            )
            require_msds = st.checkbox(
                "要求有MSDS",
                key="add_require_msds"
            )
        allow_flammable = st.checkbox(
            "允许运输易燃液体",
            key="add_allow_flammable"
        )
        if st.button(
            "添加物流规则",
            key="add_logistic_button"
        ):
            if not name or not min_days or not max_days:
                st.error("请填写所有必填字段")
            else:
                # 货币转换
                rub_rate = ExchangeRateService().get_exchange_rate()
                usd_rate = get_usd_rate()

                # 价格转换（使用统一货币单位）
                if price_currency == "卢布":
                    price_limit_cny = (
                        round(price_limit * rub_rate, 4)
                        if price_limit > 0 else 0
                    )
                    price_limit_rub = price_limit
                    price_min_rub = price_min
                else:  # 美元
                    price_limit_cny = (
                        round(price_limit * usd_rate, 4)
                        if price_limit > 0 else 0
                    )
                    price_limit_rub = price_limit
                    price_min_rub = price_min

                type_en = {"陆运": "land", "空运": "air"}[logistic_type]
                fee_mode_key = (
                    "base_plus_continue"
                    if fee_mode == "基础费用+续重费用"
                    else "first_plus_continue"
                )
                continue_unit_val = unit_map[continue_unit]

                # 送货方式映射
                delivery_method_map = {
                    "送货上门": "home_delivery",
                    "送货到取货点": "pickup_point",
                    "未知": "unknown"
                }

                insert_sql = (
                    "INSERT INTO logistics ("
                    "user_id, name, type, min_days, max_days, "
                    "price_limit, price_limit_rub, price_min_rub, "
                    "base_fee, min_weight, max_weight, "
                    "max_sum_of_sides, max_longest_side, max_second_side, "
                    "min_length, max_cylinder_sum, max_cylinder_length, "
                    "min_cylinder_length, volume_mode, "
                    "longest_side_threshold, volume_coefficient, "
                    "allow_battery, allow_flammable, "
                    "battery_capacity_limit_wh, require_msds, fee_mode, "
                    "first_fee, first_weight_g, continue_fee, continue_unit, "
                    "delivery_method, price_limit_currency, price_min_currency"
                    ") "
                    "VALUES (?,?,?,?,?,?,?, "
                    "?,?,?,?,?,?,?,?, "
                    "?,?,?,?,?,?,?,?,?, "
                    "?,?,?,?,?,?,?,?,?,?,?,?)"
                )
                c.execute(
                    insert_sql,
                    (
                        uid,
                        name,
                        type_en,
                        min_days,
                        max_days,
                        price_limit_cny,
                        price_limit_rub,
                        price_min_rub,
                        base_fee,
                        min_weight,
                        max_weight,
                        max_sum_of_sides,
                        max_longest_side,
                        max_second_side,
                        min_length,
                        max_cylinder_sum,
                        max_cylinder_length,
                        min_cylinder_length,
                        volume_mode,
                        longest_side_threshold,
                        volume_coefficient,
                        int(allow_battery),
                        int(allow_flammable),
                        battery_capacity_limit_wh,
                        int(require_msds),
                        fee_mode_key,
                        (
                            first_fee
                            if fee_mode_key == "first_plus_continue"
                            else 0.0
                        ),
                        (
                            first_weight_g
                            if fee_mode_key == "first_plus_continue"
                            else 0
                        ),
                        continue_fee,
                        continue_unit_val,
                        delivery_method_map[delivery_method],
                        price_currency,
                        price_currency,
                    ),
                )
                conn.commit()

                # 重新计算优先级分组
                calculate_and_update_priority_groups()

                st.success("物流规则添加成功！")
                st.rerun()
    # ------------------------------------------------------------------
    # 物流列表
    # ------------------------------------------------------------------
    st.subheader("物流列表")
    land_query = "SELECT * FROM logistics WHERE type='land' AND user_id = ?"
    land_df = pd.read_sql(land_query, conn, params=(uid,))

    air_query = "SELECT * FROM logistics WHERE type='air' AND user_id = ?"
    air_df = pd.read_sql(air_query, conn, params=(uid,))
    left, right = st.columns(2)
    with left:
        st.write("**陆运**")
        if not land_df.empty:
            for _, row in land_df.iterrows():
                logistics_info = (
                    f"{row['id']} | {row['name']} | "
                    f"{row['min_days']}-{row['max_days']}天 | "
                    f"三边和≤{row['max_sum_of_sides']}cm | "
                    f"最长边≤{row['max_longest_side']}cm"
                )
                st.write(logistics_info)
                col_edit, col_del = st.columns(2)
                with col_edit:
                    if st.button(
                        "编辑",
                        key=f"edit_land_{row['id']}"
                    ):
                        st.session_state.edit_logistic_id = row["id"]
                        st.rerun()
                with col_del:
                    if st.button(
                        "删除",
                        key=f"del_land_{row['id']}"
                    ):
                        c.execute(
                            "DELETE FROM logistics WHERE id=? AND user_id=?",
                            (row["id"], uid),
                        )
                        conn.commit()

                        # 重新计算优先级分组
                        calculate_and_update_priority_groups()

                        st.rerun()
        else:
            st.info("暂无陆运数据")
    with right:
        st.write("**空运**")
        if not air_df.empty:
            for _, row in air_df.iterrows():
                logistics_info = (
                    f"{row['id']} | {row['name']} | "
                    f"{row['min_days']}-{row['max_days']}天 | "
                    f"三边和≤{row['max_sum_of_sides']}cm | "
                    f"最长边≤{row['max_longest_side']}cm"
                )
                st.write(logistics_info)
                col_edit, col_del = st.columns(2)
                with col_edit:
                    if st.button(
                        "编辑",
                        key=f"edit_air_{row['id']}"
                    ):
                        st.session_state.edit_logistic_id = row["id"]
                        st.rerun()
                with col_del:
                    if st.button(
                        "删除",
                        key=f"del_air_{row['id']}"
                    ):
                        c.execute(
                            "DELETE FROM logistics WHERE id=? AND user_id=?",
                            (row["id"], uid),
                        )
                        conn.commit()

                        # 重新计算优先级分组
                        calculate_and_update_priority_groups()

                        st.rerun()
        else:
            st.info("暂无空运数据")


def edit_logistic_form():
    """物流编辑表单"""
    conn, c = get_db()
    uid = current_user_id()
    lid = st.session_state.edit_logistic_id
    row = c.execute(
        "SELECT * FROM logistics WHERE id=? AND user_id=?", (lid, uid)
    ).fetchone()
    if not row:
        st.error("规则不存在或无权编辑")
        if st.button(
            "返回",
            key=f"edit_cancel_{lid}"
        ):
            del st.session_state.edit_logistic_id
            st.rerun()
        return
    vals = dict(zip(row.keys(), row))
    st.subheader("编辑物流规则")
    name = st.text_input("物流名称", value=vals["name"], key=f"name_{lid}")
    typ = st.selectbox(
        "物流类型",
        ["陆运", "空运"],
        index=0 if vals["type"] == "land" else 1,
        key=f"type_{lid}",
    )
    min_days = st.number_input(
        "最快时效(天)",
        value=vals["min_days"],
        key=f"min_days_{lid}"
    )
    max_days = st.number_input(
        "最慢时效(天)",
        value=vals["max_days"],
        key=f"max_days_{lid}"
    )

    st.subheader("计费方式")
    fee_mode = st.radio(
        "计费方式",
        ["基础费用+续重费用", "首重费用+续重费用"],
        index=0 if vals.get("fee_mode") == "base_plus_continue" else 1,
        key=f"fee_mode_{lid}",
    )
    unit_map = {
        "克": "1",
        "50克": "50",
        "100克": "100",
        "500克": "500",
        "1千克": "1000",
    }
    unit_values = ["1", "50", "100", "500", "1000"]
    if fee_mode == "基础费用+续重费用":
        base_fee = st.number_input(
            "基础费用(元)",
            value=vals.get("base_fee", 0.0),
            key=f"base_fee_{lid}"
        )
        first_fee = 0.0
        first_weight_g = 0
        continue_fee = st.number_input(
            "续重费用(元 / 单位)",
            value=vals.get("continue_fee", 0.0),
            key=f"continue_fee_{lid}",
        )
        continue_unit = st.selectbox(
            "续重单位",
            list(unit_map.keys()),
            index=unit_values.index(vals.get("continue_unit", "100")),
            key=f"continue_unit_{lid}",
        )
    else:
        base_fee = 0.0
        first_fee = st.number_input(
            "首重费用(元)",
            value=vals.get("first_fee", 0.0),
            key=f"first_fee_{lid}"
        )
        first_weight_g = st.number_input(
            "首重重量(克)",
            min_value=0,
            value=vals.get("first_weight_g", 0),
            key=f"first_weight_g_{lid}",
        )
        continue_fee = st.number_input(
            "续重费用(元 / 单位)",
            value=vals.get("continue_fee", 0.0),
            key=f"continue_fee2_{lid}",
        )
        continue_unit = st.selectbox(
            "续重单位",
            list(unit_map.keys()),
            index=unit_values.index(vals.get("continue_unit", "100")),
            key=f"continue_unit2_{lid}",
        )

    st.subheader("重量限制")
    min_weight = st.number_input(
        "最小重量(g)",
        value=vals["min_weight"],
        key=f"min_weight_{lid}"
    )
    max_weight = st.number_input(
        "最大重量(g)",
        value=vals["max_weight"],
        key=f"max_weight_{lid}"
    )

    st.subheader("包装规定")

    # 标准包装部分
    st.write("**标准包装**")
    max_sum_of_sides = st.number_input(
        "三边之和限制(cm)",
        value=vals.get("max_sum_of_sides", 0),
        key=f"max_sum_of_sides_{lid}",
    )
    max_longest_side = st.number_input(
        "最长边限制(cm)",
        value=vals.get("max_longest_side", 0),
        key=f"max_longest_side_{lid}",
    )
    max_second_side = st.number_input(
        "第二边长上限(cm)",
        value=vals.get("max_second_side", 0),
        help="0表示不限制",
        key=f"max_second_side_{lid}",
    )
    min_length = st.number_input(
        "长度下限(cm)",
        value=vals.get("min_length", 0),
        help="0表示不限制",
        key=f"min_length_{lid}",
    )

    st.divider()

    # 圆柱形包装部分
    st.write("**圆柱形包装**")
    max_cylinder_sum = st.number_input(
        "2倍直径与长度之和限制(cm)",
        value=vals.get("max_cylinder_sum", 0),
        key=f"max_cylinder_sum_{lid}",
    )
    max_cylinder_length = st.number_input(
        "长度限制(cm)",
        value=vals.get("max_cylinder_length", 0),
        key=f"max_cylinder_length_{lid}",
    )
    min_cylinder_length = st.number_input(
        "长度下限(cm)",
        value=vals.get("min_cylinder_length", 0),
        help="0表示不限制",
        key=f"min_cylinder_length_{lid}",
    )

    st.subheader("体积重量计费方式")

    def volume_mode_format_edit(x):
        return {
            "none": "不计算体积重量",
            "max_actual_vs_volume": "取实际重量与体积重量较大者",
            "longest_side": "最长边超过阈值时按体积重量计费",
        }[x]

    volume_mode_options = [
        "none", "max_actual_vs_volume", "longest_side"
    ]
    volume_mode = st.selectbox(
        "体积重量计费方式",
        volume_mode_options,
        index=volume_mode_options.index(vals.get("volume_mode", "none")),
        format_func=volume_mode_format_edit,
        key=f"volume_mode_{lid}",
    )
    longest_side_threshold = 0
    volume_coefficient = vals.get("volume_coefficient", 5000)
    if volume_mode == "longest_side":
        longest_side_threshold = st.number_input(
            "最长边阈值(cm)",
            min_value=0,
            value=vals.get("longest_side_threshold", 0),
            key=f"longest_side_threshold_{lid}",
        )
        volume_coefficient = st.number_input(
            "体积重量系数",
            min_value=1.0,
            value=float(vals.get("volume_coefficient", 5000.0)),
            key=f"volume_coefficient_{lid}",
        )
    elif volume_mode == "max_actual_vs_volume":
        volume_coefficient = st.number_input(
            "体积重量系数",
            min_value=1.0,
            value=float(vals.get("volume_coefficient", 5000.0)),
            key=f"volume_coefficient2_{lid}",
        )

    st.subheader("送货方式")
    delivery_method_map = {
        "home_delivery": "送货上门",
        "pickup_point": "送货到取货点",
        "unknown": "未知"
    }
    delivery_method_options = [
        "送货上门", "送货到取货点", "未知"
    ]
    current_delivery = delivery_method_map.get(
        vals.get("delivery_method", "unknown"), "未知"
    )
    delivery_method = st.radio(
        "送货方式",
        delivery_method_options,
        index=delivery_method_options.index(current_delivery),
        horizontal=True,
        key=f"delivery_method_{lid}"
    )

    st.subheader("价格限制")
    col1, col2 = st.columns(2)
    with col1:
        price_limit = st.number_input(
            "价格上限",
            min_value=0.0,
            value=vals.get("price_limit_rub", 0.0),
            help=(
                "物流方给出的最高价格限制"
            ),
            key=f"price_limit_{lid}",
        )
    with col2:
        price_min = st.number_input(
            "价格下限",
            min_value=0.0,
            value=vals.get("price_min_rub", 0.0),
            help=(
                "物流方给出的最低价格限制，0表示不限制"
            ),
            key=f"price_min_{lid}",
        )
    currency_options = ["卢布", "美元"]
    currency_index = (
        0 if vals.get("price_limit_currency", "RUB") == "RUB" else 1
    )
    price_currency = st.selectbox(
        "货币单位",
        currency_options,
        index=currency_index,
        key=f"price_currency_{lid}"
    )

    st.subheader("特殊物品限制")
    allow_battery = st.checkbox(
        "允许运输含电池产品",
        value=bool(vals["allow_battery"]),
        key=f"allow_battery_{lid}"
    )
    battery_capacity_limit_wh = 0.0
    require_msds = False
    if allow_battery:
        battery_capacity_limit_wh = st.number_input(
            "电池容量限制(Wh)",
            value=vals.get("battery_capacity_limit_wh", 0.0),
            key=f"battery_capacity_limit_wh_{lid}",
        )
        require_msds = st.checkbox(
            "要求有MSDS",
            value=bool(vals.get("require_msds", 0)),
            key=f"require_msds_{lid}",
        )
    allow_flammable = st.checkbox(
        "允许运输易燃液体",
        value=bool(vals["allow_flammable"]),
        key=f"allow_flammable_{lid}",
    )
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button(
            "保存修改",
            key=f"save_{lid}"
        ):
            # 货币转换
            rub_rate = ExchangeRateService().get_exchange_rate()
            usd_rate = get_usd_rate()

            # 价格转换（使用统一货币单位）
            if price_currency == "卢布":
                price_limit_cny = (
                    round(price_limit * rub_rate, 4)
                    if price_limit > 0 else 0
                )
                price_limit_rub = price_limit
                price_min_rub = price_min
            else:  # 美元
                price_limit_cny = (
                    round(price_limit * usd_rate, 4)
                    if price_limit > 0 else 0
                )
                price_limit_rub = price_limit
                price_min_rub = price_min

            fee_mode_key = (
                "base_plus_continue"
                if fee_mode == "基础费用+续重费用"
                else "first_plus_continue"
            )
            continue_unit_val = unit_map[continue_unit]

            # 送货方式映射
            delivery_method_map = {
                "送货上门": "home_delivery",
                "送货到取货点": "pickup_point",
                "未知": "unknown"
            }
            # 构建 UPDATE 语句
            update_sql = (
                "UPDATE logistics SET "
                "name=?, type=?, min_days=?, max_days=?, "
                "price_limit=?, price_limit_rub=?, price_min_rub=?, "
                "base_fee=?, min_weight=?, max_weight=?, "
                "max_sum_of_sides=?, max_longest_side=?, "
                "max_second_side=?, min_length=?, "
                "max_cylinder_sum=?, max_cylinder_length=?, "
                "min_cylinder_length=?, volume_mode=?, "
                "longest_side_threshold=?, volume_coefficient=?, "
                "allow_battery=?, allow_flammable=?, "
                "battery_capacity_limit_wh=?, require_msds=?, "
                "fee_mode=?, first_fee=?, first_weight_g=?, "
                "continue_fee=?, continue_unit=?, "
                "delivery_method=?, price_limit_currency=?, "
                "price_min_currency=? "
                "WHERE id=? AND user_id=?"
            )
            c.execute(
                update_sql,
                (
                    name,
                    {"陆运": "land", "空运": "air"}[typ],
                    min_days,
                    max_days,
                    price_limit_cny,
                    price_limit_rub,
                    price_min_rub,
                    base_fee,
                    min_weight,
                    max_weight,
                    max_sum_of_sides,
                    max_longest_side,
                    max_second_side,
                    min_length,
                    max_cylinder_sum,
                    max_cylinder_length,
                    min_cylinder_length,
                    volume_mode,
                    longest_side_threshold,
                    volume_coefficient,
                    int(allow_battery),
                    int(allow_flammable),
                    battery_capacity_limit_wh,
                    int(require_msds),
                    fee_mode_key,
                    (
                        first_fee
                        if fee_mode_key == "first_plus_continue"
                        else 0.0
                    ),
                    (
                        first_weight_g
                        if fee_mode_key == "first_plus_continue"
                        else 0
                    ),
                    continue_fee,
                    continue_unit_val,
                    delivery_method_map[delivery_method],
                    price_currency,
                    price_currency,
                    lid,
                    uid,
                ),
            )
            conn.commit()

            # 重新计算优先级分组
            calculate_and_update_priority_groups()

            st.success("修改成功！")
            del st.session_state.edit_logistic_id
            st.rerun()
    with col_cancel:
        if st.button(
            "取消",
            key=f"cancel_{lid}"
        ):
            del st.session_state.edit_logistic_id
            st.rerun()
