import streamlit as st
import pandas as pd
from db_utils import get_db, current_user_id
from exchange_service import ExchangeRateService


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
        name = st.text_input("物流名称*")
        logistic_type = st.selectbox("物流类型*", ["陆运", "空运"])
        min_days = st.number_input("最快时效(天)*", min_value=1, value=10)
        max_days = st.number_input("最慢时效(天)*", min_value=min_days, value=30)
        price_limit_rub = st.number_input(
            "价格上限(卢布)",
            min_value=0.0,
            value=0.0,
            help="物流方给出的最高价格限制，系统会自动折算成人民币做内部记录",
        )
        price_min_rub = st.number_input(
            "价格下限(卢布)",
            min_value=0.0,
            value=0.0,
            help="物流方给出的最低价格限制，0表示不限制",
        )
        st.subheader("计费方式")
        fee_mode = st.radio("计费方式", ["基础费用+续重费用", "首重费用+续重费用"])
        unit_map = {
            "克": "1",
            "50克": "50",
            "100克": "100",
            "500克": "500",
            "1千克": "1000",
        }
        if fee_mode == "基础费用+续重费用":
            base_fee = st.number_input("基础费用(元)", value=0.0)
            continue_fee = st.number_input("续重费用(元 / 单位)", value=0.0)
            continue_unit = st.selectbox("续重单位", list(unit_map.keys()))
            first_fee, first_weight_g = 0.0, 0
        else:
            first_fee = st.number_input("首重费用(元)", value=0.0)
            first_weight_g = st.number_input("首重重量(克)", min_value=0, value=0)
            continue_fee = st.number_input("续重费用(元 / 单位)", value=0.0)
            continue_unit = st.selectbox("续重单位", list(unit_map.keys()))
            base_fee = 0.0
        st.subheader("重量限制")
        min_weight = st.number_input("最小重量(g)", value=0)
        max_weight = st.number_input("最大重量(g)", value=0)
        st.subheader("尺寸限制")
        package_type = st.radio("包装类型", ["标准包装", "圆柱形包装"], horizontal=True)
        if package_type == "标准包装":
            max_sum_of_sides = st.number_input("三边之和限制(cm)", value=0)
            max_longest_side = st.number_input("最长边限制(cm)", value=0)
            max_second_side = st.number_input(
                "第二边长上限(cm)", value=0, help="0表示不限制"
            )
            min_length = st.number_input("长度下限(cm)", value=0, help="0表示不限制")
            max_cylinder_sum = 0
            max_cylinder_length = 0
            min_cylinder_length = 0
        else:
            max_cylinder_sum = st.number_input("2倍直径与长度之和限制(cm)", value=0)
            max_cylinder_length = st.number_input("长度限制(cm)", value=0)
            min_cylinder_length = st.number_input(
                "长度下限(cm)", value=0, help="0表示不限制"
            )
            max_sum_of_sides = 0
            max_longest_side = 0
            max_second_side = 0
            min_length = 0
        volume_mode = st.selectbox(
            "体积重量计费方式",
            ["none", "max_actual_vs_volume", "longest_side"],
            format_func=lambda x: {
                "none": "不计算体积重量",
                "max_actual_vs_volume": "取实际重量与体积重量较大者",
                "longest_side": "最长边超过阈值时按体积重量计费",
            }[x],
        )
        longest_side_threshold = 0.0
        volume_coefficient = 0.0
        if volume_mode == "longest_side":
            longest_side_threshold = st.number_input(
                "最长边阈值(cm)", min_value=0.0, value=0.0
            )
            volume_coefficient = st.number_input(
                "体积重量系数", min_value=1.0, value=5000.0
            )
        elif volume_mode == "max_actual_vs_volume":
            volume_coefficient = st.number_input(
                "体积重量系数", min_value=1.0, value=5000.0
            )
        st.subheader("特殊物品限制")
        allow_battery = st.checkbox("允许运输含电池产品")
        battery_capacity_limit_wh = 0.0
        require_msds = False
        if allow_battery:
            battery_capacity_limit_wh = st.number_input(
                "电池容量限制(Wh)", min_value=0.0, value=0.0, step=0.1
            )
            require_msds = st.checkbox("要求有MSDS")
        allow_flammable = st.checkbox("允许运输易燃液体")
        if st.button("添加物流规则"):
            if not name or not min_days or not max_days:
                st.error("请填写所有必填字段")
            else:
                rate = ExchangeRateService().get_exchange_rate()
                price_limit_cny = round(price_limit_rub / rate, 4)
                type_en = {"陆运": "land", "空运": "air"}[logistic_type]
                fee_mode_key = (
                    "base_plus_continue"
                    if fee_mode == "基础费用+续重费用"
                    else "first_plus_continue"
                )
                continue_unit_val = unit_map[continue_unit]
                c.execute(
                    "INSERT INTO logistics ("
                    "user_id, name, type, min_days, max_days, "
                    "price_limit, price_limit_rub, price_min_rub, "
                    "base_fee, min_weight, max_weight, "
                    "max_sum_of_sides, max_longest_side, max_second_side, "
                    "min_length, max_cylinder_sum, max_cylinder_length, "
                    "min_cylinder_length, volume_mode,"
                    "longest_side_threshold, volume_coefficient,"
                    "allow_battery, allow_flammable,"
                    "battery_capacity_limit_wh, require_msds, fee_mode,"
                    "first_fee, first_weight_g,continue_fee, continue_unit"
                    ") "
                    "VALUES (?,?,?,?,?,?,?,"
                    "?,?,?,?,?,?,?,?,"
                    "?,?,?,?,?,?,?,?,?,"
                    "?,?,?,?,?,?,?,?,?)",
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
                    ),
                )
                conn.commit()
                st.success("物流规则添加成功！")
                st.rerun()
    # ------------------------------------------------------------------
    # 物流列表
    # ------------------------------------------------------------------
    st.subheader("物流列表")
    land_df = pd.read_sql(
        "SELECT * FROM logistics WHERE type='land' AND user_id = ?",
        conn,
        params=(uid,))
    air_df = pd.read_sql(
        "SELECT * FROM logistics WHERE type='air' AND user_id = ?",
        conn,
        params=(uid,))
    left, right = st.columns(2)
    with left:
        st.write("**陆运**")
        if not land_df.empty:
            for _, row in land_df.iterrows():
                st.write(
                    f"{row['id']} | {row['name']} | "
                    f"{row['min_days']}-{row['max_days']}天 | "
                    f"三边和≤{row['max_sum_of_sides']}cm | "
                    f"最长边≤{row['max_longest_side']}cm"
                )
                col_edit, col_del = st.columns(2)
                with col_edit:
                    if st.button("编辑", key=f"edit_land_{row['id']}"):
                        st.session_state.edit_logistic_id = row["id"]
                        st.rerun()
                with col_del:
                    if st.button("删除", key=f"del_land_{row['id']}"):
                        c.execute(
                            "DELETE FROM logistics WHERE id=? AND user_id=?",
                            (row["id"], uid),
                        )
                        conn.commit()
                        st.rerun()
        else:
            st.info("暂无陆运数据")
    with right:
        st.write("**空运**")
        if not air_df.empty:
            for _, row in air_df.iterrows():
                st.write(
                    f"{row['id']} | {row['name']} | "
                    f"{row['min_days']}-{row['max_days']}天 | "
                    f"三边和≤{row['max_sum_of_sides']}cm | "
                    f"最长边≤{row['max_longest_side']}cm"
                )
                col_edit, col_del = st.columns(2)
                with col_edit:
                    if st.button("编辑", key=f"edit_air_{row['id']}"):
                        st.session_state.edit_logistic_id = row["id"]
                        st.rerun()
                with col_del:
                    if st.button("删除", key=f"del_air_{row['id']}"):
                        c.execute(
                            "DELETE FROM logistics WHERE id=? AND user_id=?",
                            (row["id"], uid),
                        )
                        conn.commit()
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
        if st.button("返回", key=f"edit_cancel_{lid}"):
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
        "最快时效(天)", value=vals["min_days"], key=f"min_days_{lid}"
    )
    max_days = st.number_input(
        "最慢时效(天)", value=vals["max_days"], key=f"max_days_{lid}"
    )
    price_limit_rub = st.number_input(
        "价格上限(卢布)",
        min_value=0.0,
        value=vals.get("price_limit_rub", 0.0),
        key=f"price_limit_rub_{lid}",
    )
    price_min_rub = st.number_input(
        "价格下限(卢布)",
        min_value=0.0,
        value=vals.get("price_min_rub", 0.0),
        key=f"price_min_rub_{lid}",
    )
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
    if fee_mode == "基础费用+续重费用":
        base_fee = st.number_input(
            "基础费用(元)", value=vals.get("base_fee", 0.0), key=f"base_fee_{lid}"
        )
        first_fee = 0.0
        first_weight_g = 0
        continue_fee = st.number_input(
            "续重费用(元 / 单位)",
            value=vals.get("continue_fee", 0.0),
            key=f"continue_fee_{lid}",
        )
    else:
        base_fee = 0.0
        first_fee = st.number_input(
            "首重费用(元)", value=vals.get("first_fee", 0.0), key=f"first_fee_{lid}"
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
        index=[
            "1",
            "50",
            "100",
            "500",
            "1000"].index(
                vals.get("continue_unit", "100")),
        key=f"continue_unit_{lid}",
    )
    st.subheader("重量限制")
    min_weight = st.number_input(
        "最小重量(g)", value=vals["min_weight"], key=f"min_weight_{lid}"
    )
    max_weight = st.number_input(
        "最大重量(g)", value=vals["max_weight"], key=f"max_weight_{lid}"
    )
    st.subheader("尺寸限制")
    has_cylinder_limits = (
        vals.get("max_cylinder_sum", 0) > 0
        or vals.get("max_cylinder_length", 0) > 0
        or vals.get("min_cylinder_length", 0) > 0
    )
    package_type = st.radio(
        "包装类型",
        ["标准包装", "圆柱形包装"],
        index=1 if has_cylinder_limits else 0,
        horizontal=True,
        key=f"package_type_{lid}",
    )
    if package_type == "标准包装":
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
        max_cylinder_sum = 0
        max_cylinder_length = 0
        min_cylinder_length = 0
    else:
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
        max_sum_of_sides = 0
        max_longest_side = 0
        max_second_side = 0
        min_length = 0
    volume_mode = st.selectbox(
        "体积重量计费方式",
        ["none", "max_actual_vs_volume", "longest_side"],
        index=["none", "max_actual_vs_volume", "longest_side"].index(
            vals.get("volume_mode", "none")
        ),
        format_func=lambda x: {
            "none": "不计算体积重量",
            "max_actual_vs_volume": "取实际重量与体积重量较大者",
            "longest_side": "最长边超过阈值时按体积重量计费",
        }[x],
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
            key=f"volume_coefficient_{lid}",
        )
    allow_battery = st.checkbox(
        "允许电池", value=bool(vals["allow_battery"]), key=f"allow_battery_{lid}"
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
        "允许易燃液体",
        value=bool(vals["allow_flammable"]),
        key=f"allow_flammable_{lid}",
    )
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("保存修改", key=f"save_{lid}"):
            rate = ExchangeRateService().get_exchange_rate()
            price_limit_cny = round(price_limit_rub / rate, 4)
            fee_mode_key = (
                "base_plus_continue"
                if fee_mode == "基础费用+续重费用"
                else "first_plus_continue"
            )
            continue_unit_val = unit_map[continue_unit]
            c.execute(
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
                "continue_fee=?, continue_unit=? "
                "WHERE id=? AND user_id=?",
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
                    lid,
                    uid,
                ),
            )
            conn.commit()
            st.success("修改成功！")
            del st.session_state.edit_logistic_id
            st.rerun()
    with col_cancel:
        if st.button("取消", key=f"cancel_{lid}"):
            del st.session_state.edit_logistic_id
            st.rerun()
