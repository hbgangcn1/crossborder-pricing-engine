import streamlit as st
import pandas as pd
from db_utils import get_db, current_user_id


def products_page():
    """产品管理页面"""
    conn, c = get_db()
    uid = current_user_id()

    if st.session_state.get("edit_product_id"):
        edit_product_form()
        return

    # 缓存产品表
    products = pd.read_sql(
        "SELECT id, name, category, weight_g "
        "FROM products "
        "WHERE user_id = ?", conn, params=(uid,), )

    # 添加/编辑产品
    with st.expander("添加新产品", expanded=True):
        st.subheader("添加新产品")
        st.subheader("基本信息")
        name = st.text_input("产品名称*")
        russian_name = st.text_input("俄文名称")
        category = st.text_input("产品类别")
        model = st.text_input("型号")
        unit_price = st.number_input(
            "进货单价（元）*", min_value=0.0, value=0.0, step=0.01
        )
        st.subheader("物理规格")
        weight_g = st.number_input("重量(g)*", min_value=0, value=0)
        shape = st.radio("包装形状", ["标准包装", "圆柱形包装"], horizontal=True)
        is_cylinder = shape == "圆柱形包装"

        # 初始化圆柱形包装变量（用于兼容性）
        cylinder_diameter = 0.0
        cylinder_length = 0.0

        # 标准包装尺寸
        if not is_cylinder:
            col1, col2, col3 = st.columns(3)
            length_cm = col1.number_input("长(cm)*", min_value=0, value=0)
            width_cm = col2.number_input("宽(cm)*", min_value=0, value=0)
            height_cm = col3.number_input("高(cm)*", min_value=0, value=0)
        else:
            # 圆柱形包装尺寸
            col1, col2 = st.columns(2)
            cylinder_diameter = col1.number_input(
                "圆柱直径(cm)*", min_value=0.0, value=0.0
            )
            cylinder_length = col2.number_input(
                "圆柱长度(cm)*", min_value=0.0, value=0.0
            )
            # 为圆柱形包装设置默认的长宽高值（用于兼容性）
            length_cm = cylinder_diameter
            width_cm = cylinder_diameter
            height_cm = cylinder_length
        has_battery = st.checkbox("含电池")
        choice = None
        battery_capacity_wh = 0.0
        battery_capacity_mah = 0
        battery_voltage = 0.0
        if has_battery:
            choice = st.radio(
                "电池容量填写方式", ["填写 Wh（瓦时）", "填写 mAh + V"], horizontal=True
            )
            if choice == "填写 Wh（瓦时）":
                battery_capacity_wh = st.number_input(
                    "电池容量(Wh)*", min_value=0.0, value=0.0
                )
            else:
                col1, col2 = st.columns(2)
                battery_capacity_mah = col1.number_input(
                    "电池容量(mAh)*", min_value=0, value=0
                )
                battery_voltage = col2.number_input(
                    "电池电压(V)*", min_value=0.0, value=0.0
                )
                # 电池容量验证警告
                if battery_capacity_mah > 0 and battery_voltage <= 0:
                    st.warning("请填写电池电压(V)")
                elif battery_voltage > 0 and battery_capacity_mah <= 0:
                    st.warning("请填写电池容量(mAh)")
        col1, col2 = st.columns(2)
        has_msds = col1.checkbox("有MSDS文件")
        has_flammable = col2.checkbox("有易燃液体")
        shipping_fee = col1.number_input("发货方运费(元)", min_value=0.0, value=0.0)
        labeling_fee = st.number_input("代贴单费用(元)", min_value=0.0, value=0.0)
        st.subheader("定价参数")
        col1, col2 = st.columns(2)
        promotion_discount = col2.slider(
            "活动折扣率", 0.0, 100.0, 5.0, 1.0, format="%.1f%%"
        ) / 100.0
        promotion_cost_rate = col1.slider(
            "推广费用率", 0.0, 100.0, 11.5, 1.0, format="%.1f%%"
        ) / 100.0
        target_profit_margin = col1.slider(
            "目标利润率", 0.0, 100.0, 50.0, 1.0, format="%.1f%%"
        ) / 100.0
        commission_rate = col2.slider(
            "佣金率", 0.0, 100.0, 17.5, 1.0, format="%.1f%%"
        ) / 100.0
        withdrawal_fee_rate = col1.slider(
            "提现费率", 0.0, 100.0, 1.0, 1.0, format="%.1f%%"
        ) / 100.0
        payment_processing_fee = col2.slider(
            "支付手续费率", 0.0, 100.0, 1.3, 1.0, format="%.1f%%"
        ) / 100.0
        if st.button("添加产品"):
            required = [
                name,
                weight_g,
                unit_price]
            if not is_cylinder:
                required.extend([length_cm, width_cm, height_cm])
            else:
                required.extend([cylinder_diameter, cylinder_length])
            # 电池容量验证逻辑
            if has_battery:
                if choice == "填写 Wh（瓦时）":
                    if battery_capacity_wh <= 0:
                        # 如果填写了Wh但值为0，跳过电池容量限制判断
                        pass
                elif choice == "填写 mAh + V":
                    if battery_capacity_mah > 0 and battery_voltage <= 0:
                        required.append(None)
                    elif battery_voltage > 0 and battery_capacity_mah <= 0:
                        required.append(None)
                    elif battery_capacity_mah <= 0 and battery_voltage <= 0:
                        # 如果都填了0，跳过电池容量限制判断
                        pass
                    else:
                        # 正常情况，不需要额外验证
                        pass
            # 检查必填字段
            missing_fields = []
            if not name:
                missing_fields.append("产品名称")
            if weight_g <= 0:
                missing_fields.append("重量")
            if unit_price <= 0:
                missing_fields.append("进货单价")
            if not is_cylinder:
                if length_cm <= 0:
                    missing_fields.append("长度")
                if width_cm <= 0:
                    missing_fields.append("宽度")
                if height_cm <= 0:
                    missing_fields.append("高度")
            else:
                if cylinder_diameter <= 0:
                    missing_fields.append("圆柱直径")
                if cylinder_length <= 0:
                    missing_fields.append("圆柱长度")
            # 电池容量验证逻辑
            if has_battery:
                if choice == "填写 Wh（瓦时）":
                    if battery_capacity_wh <= 0:
                        # 如果填写了Wh但值为0，跳过电池容量限制判断
                        pass
                elif choice == "填写 mAh + V":
                    if battery_capacity_mah > 0 and battery_voltage <= 0:
                        missing_fields.append("电池电压(V)")
                    elif battery_voltage > 0 and battery_capacity_mah <= 0:
                        missing_fields.append("电池容量(mAh)")
                    elif battery_capacity_mah <= 0 and battery_voltage <= 0:
                        # 如果都填了0，跳过电池容量限制判断
                        pass
                    else:
                        # 正常情况，不需要额外验证
                        pass

            if missing_fields:
                st.error(f"请填写以下必填字段：{', '.join(missing_fields)}")
            else:
                c.execute(
                    "INSERT INTO products ("
                    "user_id, name, russian_name, category, model, "
                    "weight_g, length_cm, width_cm, height_cm, "
                    "is_cylinder, cylinder_diameter, cylinder_length, "
                    "has_battery, battery_capacity_wh, battery_capacity_mah, "
                    "battery_voltage, has_msds, has_flammable, "
                    "unit_price, shipping_fee, labeling_fee, "
                    "promotion_discount, promotion_cost_rate, "
                    "target_profit_margin, commission_rate, "
                    "withdrawal_fee_rate, payment_processing_fee) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uid,
                        name,
                        russian_name,
                        category,
                        model,
                        weight_g,
                        length_cm,
                        width_cm,
                        height_cm,
                        int(is_cylinder),
                        cylinder_diameter,
                        cylinder_length if is_cylinder else 0.0,
                        int(has_battery),
                        battery_capacity_wh,
                        battery_capacity_mah,
                        battery_voltage,
                        int(has_msds),
                        int(has_flammable),
                        unit_price,
                        shipping_fee,
                        labeling_fee,
                        promotion_discount,
                        promotion_cost_rate,
                        target_profit_margin,
                        commission_rate,
                        withdrawal_fee_rate,
                        payment_processing_fee,
                    ),
                )
                conn.commit()
                st.success("产品添加成功！")
                st.session_state.products_data = pd.read_sql(
                    "SELECT id, name, category, weight_g "
                    "FROM products "
                    "WHERE user_id = ?",
                    conn,
                    params=(uid,),
                )
                st.rerun()
    # 产品列表
    st.subheader("产品列表")
    if not products.empty:
        selected_list = []
        for _, row in products.iterrows():
            if st.checkbox(
                f"{row['id']} - {row['name']} "
                f"({row['category']}, {row['weight_g']}g)",
                key=f"product_checkbox_{row['id']}",
            ):
                selected_list.append(row.to_dict())
        if selected_list:
            product_id = selected_list[0]["id"]
            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("编辑产品", key=f"edit_btn_{product_id}"):
                    st.session_state.edit_product_id = product_id
                    st.rerun()
            with col_del:
                if st.button("删除产品", key=f"del_btn_{product_id}"):
                    c.execute(
                        "DELETE FROM products WHERE id=? AND user_id=?",
                        (product_id, uid),
                    )
                    conn.commit()
                    st.session_state.products_data = pd.read_sql(
                        "SELECT id, name, category, weight_g "
                        "FROM products "
                        "WHERE user_id = ?",
                        conn,
                        params=(uid,),
                    )
                    st.rerun()
    else:
        st.info("暂无产品数据")


def edit_product_form():
    """编辑产品表单"""
    conn, c = get_db()
    uid = current_user_id()
    pid = st.session_state.edit_product_id
    row = c.execute(
        "SELECT * FROM products WHERE id=? AND user_id=?", (pid, uid)
    ).fetchone()
    if not row:
        st.error("产品不存在或无权编辑")
        if st.button("返回列表"):
            del st.session_state.edit_product_id
            st.rerun()
        return
    vals = dict(zip(row.keys(), row))
    st.subheader("编辑产品")
    name = st.text_input("产品名称*", value=vals["name"])
    russian_name = st.text_input("俄文名称", value=vals["russian_name"])
    category = st.text_input("产品类别", value=vals["category"])
    model = st.text_input("型号", value=vals["model"])
    unit_price = st.number_input(
        "进货单价（元）*", min_value=0.0, value=float(vals["unit_price"]), step=0.01
    )
    weight_g = st.number_input("重量(g)*", min_value=0, value=vals["weight_g"])
    shape = st.radio(
        "包装形状",
        ["标准包装", "圆柱形包装"],
        index=1 if vals["is_cylinder"] else 0,
        horizontal=True,
    )
    is_cylinder = shape == "圆柱形包装"

    # 初始化圆柱形包装变量（用于兼容性）
    cylinder_diameter = 0.0
    cylinder_length = 0.0

    # 标准包装尺寸
    if not is_cylinder:
        col1, col2, col3 = st.columns(3)
        length_cm = col1.number_input(
            "长(cm)*", min_value=0, value=vals["length_cm"])
        width_cm = col2.number_input(
            "宽(cm)*", min_value=0, value=vals["width_cm"]
        )
        height_cm = col3.number_input(
            "高(cm)*", min_value=0, value=vals["height_cm"])
    else:
        # 圆柱形包装尺寸
        col1, col2 = st.columns(2)
        cylinder_diameter = col1.number_input(
            "圆柱直径(cm)*", min_value=0.0, value=float(vals["cylinder_diameter"])
        )
        cylinder_length = col2.number_input(
            "圆柱长度(cm)*",
            min_value=0.0,
            value=float(vals.get("cylinder_length", 0.0))
        )
        # 为圆柱形包装设置默认的长宽高值（用于兼容性）
        length_cm = cylinder_diameter
        width_cm = cylinder_diameter
        height_cm = cylinder_length
    has_battery = st.checkbox("含电池", value=bool(vals["has_battery"]))
    choice = None
    battery_capacity_wh = 0.0
    battery_capacity_mah = 0
    battery_voltage = 0.0
    if has_battery:
        choice = st.radio(
            "电池容量填写方式",
            ["填写 Wh（瓦时）", "填写 mAh + V"],
            index=0 if vals["battery_capacity_wh"] > 0 else 1,
            horizontal=True,
        )
        if choice == "填写 Wh（瓦时）":
            battery_capacity_wh = st.number_input(
                "电池容量(Wh)*",
                min_value=0.0,
                value=float(
                    vals["battery_capacity_wh"]))
        else:
            col1, col2 = st.columns(2)
            battery_capacity_mah = col1.number_input(
                "电池容量(mAh)*", min_value=0, value=vals["battery_capacity_mah"]
            )
            battery_voltage = col2.number_input(
                "电池电压(V)*", min_value=0.0, value=float(vals["battery_voltage"])
            )
            # 电池容量验证警告
            if battery_capacity_mah > 0 and battery_voltage <= 0:
                st.warning("请填写电池电压(V)")
            elif battery_voltage > 0 and battery_capacity_mah <= 0:
                st.warning("请填写电池容量(mAh)")
    col1, col2 = st.columns(2)
    has_msds = col1.checkbox("有MSDS文件", value=bool(vals["has_msds"]))
    has_flammable = col2.checkbox("有易燃液体", value=bool(vals["has_flammable"]))
    shipping_fee = col1.number_input(
        "发货方运费(元)", min_value=0.0, value=float(vals["shipping_fee"])
    )
    labeling_fee = st.number_input(
        "代贴单费用(元)", min_value=0.0, value=float(vals["labeling_fee"])
    )
    col1, col2 = st.columns(2)
    promotion_discount = col2.slider(
        "活动折扣率", 0.0, 100.0,
        float(vals["promotion_discount"]) * 100.0, 1.0, format="%.1f%%"
    ) / 100.0
    promotion_cost_rate = col1.slider(
        "推广费用率", 0.0, 100.0,
        float(vals["promotion_cost_rate"]) * 100.0, 1.0, format="%.1f%%"
    ) / 100.0
    target_profit_margin = col1.slider(
        "目标利润率", 0.0, 100.0,
        float(vals["target_profit_margin"]) * 100.0, 1.0, format="%.1f%%"
    ) / 100.0
    commission_rate = col2.slider(
        "佣金率", 0.0, 100.0,
        float(vals["commission_rate"]) * 100.0, 1.0, format="%.1f%%"
    ) / 100.0
    withdrawal_fee_rate = col1.slider(
        "提现费率", 0.0, 100.0,
        float(vals["withdrawal_fee_rate"]) * 100.0, 1.0, format="%.1f%%"
    ) / 100.0
    payment_processing_fee = col2.slider(
        "支付手续费率", 0.0, 100.0,
        float(vals["payment_processing_fee"]) * 100.0, 1.0, format="%.1f%%"
    ) / 100.0
    if st.button("保存修改"):
        required = [name, weight_g, unit_price]
        if not is_cylinder:
            required.extend([length_cm, width_cm, height_cm])
        else:
            required.extend([cylinder_diameter, cylinder_length])
        # 电池容量验证逻辑
        if has_battery:
            if choice == "填写 Wh（瓦时）":
                if battery_capacity_wh <= 0:
                    # 如果填写了Wh但值为0，跳过电池容量限制判断
                    pass
            elif choice == "填写 mAh + V":
                if battery_capacity_mah > 0 and battery_voltage <= 0:
                    required.append(None)
                elif battery_voltage > 0 and battery_capacity_mah <= 0:
                    required.append(None)
                elif battery_capacity_mah <= 0 and battery_voltage <= 0:
                    # 如果都填了0，跳过电池容量限制判断
                    pass
                else:
                    # 正常情况，不需要额外验证
                    pass
        # 检查必填字段
        missing_fields = []
        if not name:
            missing_fields.append("产品名称")
        if weight_g <= 0:
            missing_fields.append("重量")
        if unit_price <= 0:
            missing_fields.append("进货单价")
        if not is_cylinder:
            if length_cm <= 0:
                missing_fields.append("长度")
            if width_cm <= 0:
                missing_fields.append("宽度")
            if height_cm <= 0:
                missing_fields.append("高度")
        else:
            if cylinder_diameter <= 0:
                missing_fields.append("圆柱直径")
            if cylinder_length <= 0:
                missing_fields.append("圆柱长度")
        # 电池容量验证逻辑
        if has_battery:
            if choice == "填写 Wh（瓦时）":
                if battery_capacity_wh <= 0:
                    # 如果填写了Wh但值为0，跳过电池容量限制判断
                    pass
            elif choice == "填写 mAh + V":
                if battery_capacity_mah > 0 and battery_voltage <= 0:
                    missing_fields.append("电池电压(V)")
                elif battery_voltage > 0 and battery_capacity_mah <= 0:
                    missing_fields.append("电池容量(mAh)")
                elif battery_capacity_mah <= 0 and battery_voltage <= 0:
                    # 如果都填了0，跳过电池容量限制判断
                    pass
                else:
                    # 正常情况，不需要额外验证
                    pass

        if missing_fields:
            st.error(f"请填写以下必填字段：{', '.join(missing_fields)}")
        else:
            c.execute(
                """UPDATE products SET
                    name=?, russian_name=?, category=?, model=?,
                    weight_g=?, length_cm=?, width_cm=?, height_cm=?,
                    is_cylinder=?, cylinder_diameter=?, cylinder_length=?,
                    has_battery=?, battery_capacity_wh=?,
                    battery_capacity_mah=?, battery_voltage=?,
                    has_msds=?, has_flammable=?,
                    unit_price=?, shipping_fee=?, labeling_fee=?,
                    promotion_discount=?, promotion_cost_rate=?,
                    target_profit_margin=?, commission_rate=?,
                    withdrawal_fee_rate=?, payment_processing_fee=?
                WHERE id=? AND user_id=?""",
                (
                    name,
                    russian_name,
                    category,
                    model,
                    weight_g,
                    length_cm,
                    width_cm,
                    height_cm,
                    int(is_cylinder),
                    cylinder_diameter,
                    cylinder_length if is_cylinder else 0.0,
                    int(has_battery),
                    battery_capacity_wh,
                    battery_capacity_mah,
                    battery_voltage,
                    int(has_msds),
                    int(has_flammable),
                    unit_price,
                    shipping_fee,
                    labeling_fee,
                    promotion_discount,
                    promotion_cost_rate,
                    target_profit_margin,
                    commission_rate,
                    withdrawal_fee_rate,
                    payment_processing_fee,
                    pid,
                    uid,
                ),
            )
            conn.commit()
            st.success("产品修改成功！")
            del st.session_state.edit_product_id
            st.rerun()
    if st.button("取消"):
        del st.session_state.edit_product_id
        st.rerun()
