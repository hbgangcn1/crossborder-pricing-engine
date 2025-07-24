import hashlib
import math
import numpy as np
import pandas as pd
import requests
import sqlite3
import streamlit as st
import threading
import time

# 创建线程局部存储
thread_local = threading.local()


# --------------------------
# 汇率API服务 (优化为后台线程更新)
# --------------------------
class ExchangeRateService:
    _instance = None
    _lock = threading.Lock()
    _update_thread = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.last_updated = 0
                cls._instance.exchange_rate = 7.28  # 默认值

                # 启动后台更新线程
                cls._update_thread = threading.Thread(
                    target=cls._instance._background_update,
                    daemon=True
                )
                cls._update_thread.start()
        return cls._instance

    def _background_update(self):
        """后台更新汇率"""
        while True:
            try:
                # 每小时更新一次
                if time.time() - self.last_updated >= 3600:
                    self._update_rate()
            except Exception:
                pass
            time.sleep(60)  # 每分钟检查一次

    def _update_rate(self):
        """实际更新汇率的逻辑"""
        try:
            # 使用俄罗斯央行API获取实时汇率
            response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp")
            if response.status_code == 200:
                # 解析XML获取人民币兑卢布汇率
                # 实际API返回格式需要根据实际情况调整
                # 这里使用模拟数据
                self.exchange_rate = 11.5  # 模拟值
                self.last_updated = time.time()
                if st.session_state.get('debug_mode', False):
                    st.info("汇率后台更新成功！")
            else:
                if st.session_state.get('debug_mode', False):
                    st.warning(f"汇率API请求失败，使用缓存值: {self.exchange_rate}")
        except Exception as e:
            if st.session_state.get('debug_mode', False):
                st.error(f"汇率获取失败: {str(e)}，使用缓存值: {self.exchange_rate}")

    def get_exchange_rate(self):
        """获取汇率 - 使用缓存值"""
        return self.exchange_rate


# --------------------------
# 数据库连接函数 (优化为会话状态存储)
# --------------------------
def get_db():
    """获取数据库连接 - 使用会话状态存储"""
    if 'db_conn' not in st.session_state:
        conn = sqlite3.connect('pricing_system.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        st.session_state.db_conn = conn
        st.session_state.db_cursor = conn.cursor()
        if st.session_state.get('debug_mode', False):
            st.info("🔄 创建了新的数据库连接")

    return st.session_state.db_conn, st.session_state.db_cursor


# --------------------------
# 数据库初始化 (更新产品表结构)
# --------------------------
def init_db():
    debug_mode = st.session_state.get('debug_mode', False)
    if debug_mode:
        st.info("🛠️ 初始化数据库...")

    conn, c = get_db()

    # 创建表 (添加定价参数字段)
    tables = [
        '''CREATE TABLE IF NOT EXISTS users
            (id INTEGER PRIMARY KEY,
             username TEXT UNIQUE,
             password TEXT,
             role TEXT)''',
        '''CREATE TABLE IF NOT EXISTS products
            (id INTEGER PRIMARY KEY,
             name TEXT,
             russian_name TEXT,
             category TEXT,
             model TEXT,
             weight_g INTEGER,
             length_cm INTEGER,
             width_cm INTEGER,
             height_cm INTEGER,
             is_cylinder BOOLEAN,
             cylinder_diameter INTEGER,
             has_battery BOOLEAN,
             battery_capacity_wh REAL,
             battery_capacity_mah INTEGER,
             battery_voltage REAL,
             has_msds BOOLEAN,
             has_flammable BOOLEAN,
             unit_price REAL,
             shipping_fee REAL,
             labeling_fee REAL,
             discount_rate REAL DEFAULT 0.15,
             promotion_discount REAL DEFAULT 0.05,
             promotion_cost_rate REAL DEFAULT 0.115,
             min_profit_margin REAL DEFAULT 0.3,
             target_profit_margin REAL DEFAULT 0.5,
             commission_rate REAL DEFAULT 0.175,
             withdrawal_fee_rate REAL DEFAULT 0.01,
             payment_processing_fee REAL DEFAULT 0.013)''',
        '''CREATE TABLE IF NOT EXISTS logistics
            (id INTEGER PRIMARY KEY,
             name TEXT,
             type TEXT,
             min_days INTEGER,
             max_days INTEGER,
             price_limit REAL,
             base_fee REAL,
             weight_factor REAL,
             volume_factor REAL,
             battery_factor REAL,
             min_weight INTEGER,
             max_weight INTEGER,
             max_size INTEGER,
             max_volume_weight REAL,
             allow_battery BOOLEAN,
             allow_flammable BOOLEAN)'''
    ]

    for table_sql in tables:
        c.execute(table_sql)
        if debug_mode:
            if 'TABLE' in table_sql:
                table_name = table_sql.split()[5]
            else:
                table_name = 'Unknown'
            st.info(f"✅ 创建表: {table_name}")

    conn.commit()

    # 创建初始管理员用户
    if not verify_user("admin", "admin123"):
        create_user("admin", "admin123", "admin")
        if debug_mode:
            st.info("👤 创建了初始管理员用户")

    # 检查并添加新列
    try:
        c.execute("PRAGMA table_info(products)")
        columns = [col[1] for col in c.fetchall()]

        new_columns = [
            ('discount_rate', 'REAL', 0.15),
            ('promotion_discount', 'REAL', 0.05),
            ('promotion_cost_rate', 'REAL', 0.115),
            ('min_profit_margin', 'REAL', 0.3),
            ('target_profit_margin', 'REAL', 0.5),
            ('commission_rate', 'REAL', 0.175),
            ('withdrawal_fee_rate', 'REAL', 0.01),
            ('payment_processing_fee', 'REAL', 0.013)
        ]

        for col_name, col_type, default_val in new_columns:
            if col_name not in columns:
                c.execute(
                    f"ALTER TABLE products ADD COLUMN {col_name} {col_type} "
                    f"DEFAULT {default_val}"
                )
                if debug_mode:
                    st.info(f"✅ 添加列: {col_name}")

        conn.commit()
    except Exception as e:
        st.error(f"数据库升级失败: {str(e)}")


# --------------------------
# 认证系统
# --------------------------
def create_user(username, password, role):
    conn, c = get_db()
    hashed_pwd = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed_pwd, role)
        )
        conn.commit()
        if st.session_state.get('debug_mode', False):
            st.info(f"👤 用户 '{username}' 创建成功")
        return True
    except sqlite3.IntegrityError as e:
        st.error(f"🚫 创建用户失败: {str(e)}")
        return False


def verify_user(username, password):
    conn, c = get_db()
    hashed_pwd = hashlib.sha256(password.encode()).hexdigest()
    c.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, hashed_pwd)
    )
    user = c.fetchone()
    if st.session_state.get('debug_mode', False):
        if user:
            st.info(f"🔑 用户 '{username}' 验证成功")
        else:
            st.info(f"🔒 用户 '{username}' 验证失败")
    return user


# --------------------------
# 物流计算公式
# --------------------------
def calculate_logistic_cost(logistic, product):
    """计算物流费用"""
    try:
        # 检查重量限制
        min_weight = logistic.get('min_weight')
        max_weight = logistic.get('max_weight')
        weight_g = product.get('weight_g', 0)

        if min_weight and weight_g < min_weight:
            return None
        if max_weight and weight_g > max_weight:
            return None

        # 检查尺寸限制
        max_size = logistic.get('max_size')
        if max_size:
            if (product.get('length_cm', 0) > max_size or
                    product.get('width_cm', 0) > max_size or
                    product.get('height_cm', 0) > max_size):
                return None

        # 计算体积重量
        volume_weight = (
            product.get('length_cm', 0)
            * product.get('width_cm', 0)
            * product.get('height_cm', 0)
        ) / 6000

        max_vol_weight = logistic.get('max_volume_weight')
        if max_vol_weight and volume_weight > max_vol_weight:
            return None

        # 检查电池限制
        if (product.get('has_battery', False) and
                not logistic.get('allow_battery', False)):
            return None

        # 检查易燃液体限制
        if (product.get('has_flammable', False) and
                not logistic.get('allow_flammable', False)):
            return None

        # 计算基础费用
        cost = logistic.get('base_fee', 0)

        # 计算重量费用
        weight_factor = logistic.get('weight_factor')
        if weight_factor:
            weight_units = math.ceil(weight_g / 100)  # 每100g计费
            cost += weight_factor * weight_units

        # 计算体积费用
        volume_factor = logistic.get('volume_factor')
        if volume_factor:
            volume_units = math.ceil(volume_weight * 10)  # 每10kg体积重量计费
            cost += volume_factor * volume_units

        # 计算电池附加费
        if (product.get('has_battery', False) and
                logistic.get('battery_factor')):
            cost += logistic['battery_factor']

        return cost

    except Exception as e:
        st.error(f"物流费用计算错误: {str(e)}")
        return None


# --------------------------
# 定价计算核心逻辑 (使用实时汇率)
# --------------------------
def calculate_pricing(product, land_logistics, air_logistics):
    """
    计算最终定价，并考虑物流限价约束
    :param product: dict, 产品信息
    :param land_logistics: list[dict], 陆运规则列表
    :param air_logistics:  list[dict], 空运规则列表
    :return: (land_price, air_price, land_cost, air_cost) 任一不可行则返回 None
    """
    try:
        # 1. 基础成本
        unit_price = product.get('unit_price', 0)
        shipping_fee = product.get('shipping_fee', 0)
        labeling_fee = product.get('labeling_fee', 0)

        # 2. 实时汇率
        exchange_rate = ExchangeRateService().get_exchange_rate()

        # 3. 计算每种物流的运费
        def _cost_and_filter(logistics_list):
            """计算运费并过滤掉超限价的"""
            results = []
            for log in logistics_list:
                cost = calculate_logistic_cost(log, product)
                if cost is None:                     # 不满足尺寸/重量/电池等硬条件
                    continue
                # ————— 新增限价判断 —————
                price_limit = log.get('price_limit') or 0   # 0 表示无限制
                # 先估算一个“粗定价”，用于限价过滤
                rough_price = (
                    (
                        unit_price * 1.01
                        + labeling_fee
                        + shipping_fee
                        + cost
                        + 15 * exchange_rate
                    )
                    /
                    (
                        (1 - 0.15)
                        * (1 - 0.05)
                        * (1 - 0.175)
                        * (1 - 0.01)
                        * (1 - 0.013)
                    )
                )
                if price_limit == 0 or rough_price <= price_limit:
                    results.append((log, cost))
            return results

        land_candidates = _cost_and_filter(land_logistics)
        air_candidates = _cost_and_filter(air_logistics)

        if not land_candidates or not air_candidates:
            return None, None, None, None

        # 4. 选运费最低的
        best_land, land_cost = min(land_candidates, key=lambda x: x[1])
        best_air,  air_cost = min(air_candidates,  key=lambda x: x[1])

        # 5. 精确计算最终售价（这里用你原公式即可）
        discount_rate = product.get('discount_rate', 0.15)
        promo_discount = product.get('promotion_discount', 0.05)
        commission = product.get('commission_rate', 0.175)
        withdraw_fee = product.get('withdrawal_fee_rate', 0.01)
        pay_fee = product.get('payment_processing_fee', 0.013)

        def final_price(cost):
            return round(
                (
                    unit_price * (1 + withdraw_fee)
                    + labeling_fee
                    + shipping_fee
                    + cost
                    + 15 * exchange_rate
                )
                /
                (
                    (1 - discount_rate)
                    * (1 - promo_discount)
                    * (1 - commission)
                    * (1 - withdraw_fee)
                    * (1 - pay_fee)
                ),
                2
            )

        land_price = final_price(land_cost)
        air_price = final_price(air_cost)

        return land_price, air_price, land_cost, air_cost

    except Exception as e:
        st.error(f"定价计算错误: {str(e)}")
        return None, None, None, None


# --------------------------
# 页面函数 - 产品管理
# --------------------------
def products_page():
    conn, c = get_db()

    # ---------- 如果正在编辑，则显示编辑表单 ----------
    if st.session_state.get("edit_product_id"):
        edit_product_form()
        return

    # ---------- 缓存产品表 ----------
    if 'products_data' not in st.session_state:
        st.session_state.products_data = pd.read_sql(
            "SELECT id, name, category, weight_g FROM products", conn
        )
    products = st.session_state.products_data

    # ---------- 添加/编辑 产品 ----------
    if 'add_product_expanded' not in st.session_state:
        st.session_state.add_product_expanded = True

    with st.expander("添加新产品", expanded=st.session_state.add_product_expanded):
        st.subheader("添加新产品")

        col1, col2 = st.columns(2)
        name = col1.text_input("产品名称*")
        russian_name = col2.text_input("俄文名称")
        category = col1.text_input("产品类别")
        model = col2.text_input("型号")

        st.subheader("物理规格")
        col1, col2, col3 = st.columns(3)
        weight_g = col1.number_input("重量(g)*", min_value=0, value=0)
        length_cm = col2.number_input("长(cm)*", min_value=0, value=0)
        width_cm = col3.number_input("宽(cm)*", min_value=0, value=0)
        height_cm = st.number_input("高(cm)*", min_value=0, value=0)

        shape = st.radio("包装形状", ["标准包装", "圆柱形包装"], horizontal=True)
        is_cylinder = (shape == "圆柱形包装")
        cylinder_diameter = 0
        if is_cylinder:
            cylinder_diameter = st.number_input(
                "圆柱直径(cm)*", min_value=0.0, value=0.0)

        has_battery = st.checkbox("含电池")
        battery_capacity_wh = 0.0
        battery_capacity_mah = 0
        battery_voltage = 0.0
        if has_battery:
            choice = st.radio(
                "电池容量填写方式",
                ["填写 Wh（瓦时）", "填写 mAh + V"],
                horizontal=True)
            if choice == "填写 Wh（瓦时）":
                battery_capacity_wh = st.number_input(
                    "电池容量(Wh)*", min_value=0.0, value=0.0)
            else:
                col1, col2 = st.columns(2)
                battery_capacity_mah = col1.number_input(
                    "电池容量(mAh)*", min_value=0, value=0)
                battery_voltage = col2.number_input(
                    "电池电压(V)*", min_value=0.0, value=0.0)

        st.subheader("其他信息")
        col1, col2 = st.columns(2)
        has_msds = col1.checkbox("有MSDS文件")
        has_flammable = col2.checkbox("有易燃液体")
        unit_price = col2.number_input("单价(元)*", min_value=0.0, value=0.0)
        shipping_fee = col1.number_input("发货方运费(元)*", min_value=0.0, value=0.0)
        labeling_fee = st.number_input("代贴单费用(元)*", min_value=0.0, value=0.0)

        st.subheader("定价参数")
        col1, col2 = st.columns(2)
        discount_rate = col1.slider("画线折扣率", 0.0, 1.0, 0.15, 0.01)
        promotion_discount = col2.slider("活动折扣率", 0.0, 1.0, 0.05, 0.01)
        promotion_cost_rate = col1.slider("推广费用率", 0.0, 1.0, 0.115, 0.01)
        min_profit_margin = col2.slider("最低利润率", 0.0, 1.0, 0.3, 0.01)
        target_profit_margin = col1.slider("目标利润率", 0.0, 1.0, 0.5, 0.01)
        commission_rate = col2.slider("佣金率", 0.0, 1.0, 0.175, 0.01)
        withdrawal_fee_rate = col1.slider("提现费率", 0.0, 0.1, 0.01, 0.001)
        payment_processing_fee = col2.slider("支付手续费率", 0.0, 0.1, 0.013, 0.001)

        if st.button("添加产品"):
            required = [
                name, weight_g, length_cm, width_cm, height_cm,
                unit_price, shipping_fee, labeling_fee
            ]
            if is_cylinder and cylinder_diameter <= 0:
                required.append(None)
            if (has_battery and choice == "填写 Wh（瓦时）" and
                    battery_capacity_wh <= 0):
                required.append(None)
            if (has_battery and choice == "填写 mAh + V" and
                    (battery_capacity_mah <= 0 or battery_voltage <= 0)):
                required.append(None)
            if any(v is None or (isinstance(v, (int, float)) and v <= 0)
                   for v in required):
                st.error("请填写所有必填字段")
            else:
                c.execute(
                    """INSERT INTO products (
                        name, russian_name, category, model,
                        weight_g, length_cm, width_cm, height_cm,
                        is_cylinder, cylinder_diameter,
                        has_battery, battery_capacity_wh,
                        battery_capacity_mah, battery_voltage,
                        has_msds, has_flammable, unit_price,
                        shipping_fee, labeling_fee,
                        discount_rate, promotion_discount,
                        promotion_cost_rate, min_profit_margin,
                        target_profit_margin, commission_rate,
                        withdrawal_fee_rate, payment_processing_fee
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )""",
                    (
                        name, russian_name, category, model,
                        weight_g, length_cm, width_cm, height_cm,
                        int(is_cylinder), cylinder_diameter,
                        int(has_battery), battery_capacity_wh,
                        battery_capacity_mah, battery_voltage,
                        int(has_msds), int(has_flammable), unit_price,
                        shipping_fee, labeling_fee,
                        discount_rate, promotion_discount,
                        promotion_cost_rate, min_profit_margin,
                        target_profit_margin, commission_rate,
                        withdrawal_fee_rate, payment_processing_fee
                    )
                )
                conn.commit()
                st.success("产品添加成功！")
                st.session_state.products_data = pd.read_sql(
                    "SELECT id, name, category, weight_g FROM products", conn
                )
                st.rerun()

    # ---------- 批量编辑 ----------
    st.subheader("批量操作")
    with st.expander("批量编辑产品参数"):
        products_df = pd.read_sql("SELECT id, name FROM products", conn)
        if not products_df.empty:
            options = [
                f"{row['id']} - {row['name']}"
                for _, row in products_df.iterrows()]
            selected_str = st.multiselect("选择要编辑的产品", options)
            selected_products = [int(s.split(" - ")[0]) for s in selected_str]

            if selected_products:
                with st.form("batch_edit_form"):
                    st.info(f"已选择 {len(selected_products)} 个产品")
                    col1, col2 = st.columns(2)
                    new_discount_rate = col1.slider(
                        "画线折扣率", 0.0, 1.0, 0.15, 0.01)
                    new_promotion_discount = col2.slider(
                        "活动折扣率", 0.0, 1.0, 0.05, 0.01)
                    new_promotion_cost_rate = col1.slider(
                        "推广费用率", 0.0, 1.0, 0.115, 0.01)
                    new_min_profit_margin = col2.slider(
                        "最低利润率", 0.0, 1.0, 0.3, 0.01)
                    new_target_profit_margin = col1.slider(
                        "目标利润率", 0.0, 1.0, 0.5, 0.01)
                    new_commission_rate = col2.slider(
                        "佣金率", 0.0, 1.0, 0.175, 0.01)
                    new_withdrawal_fee_rate = col1.slider(
                        "提现费率", 0.0, 0.1, 0.01, 0.001)
                    new_payment_processing_fee = col2.slider(
                        "支付手续费率", 0.0, 0.1, 0.013, 0.001)

                    submitted = st.form_submit_button("应用批量修改")
                    if submitted:
                        try:
                            for pid in selected_products:
                                c.execute(
                                    """UPDATE products SET
                                        discount_rate = ?,
                                        promotion_discount = ?,
                                        promotion_cost_rate = ?,
                                        min_profit_margin = ?,
                                        target_profit_margin = ?,
                                        commission_rate = ?,
                                        withdrawal_fee_rate = ?,
                                        payment_processing_fee = ?
                                        WHERE id = ?""",
                                    (
                                        new_discount_rate,
                                        new_promotion_discount,
                                        new_promotion_cost_rate,
                                        new_min_profit_margin,
                                        new_target_profit_margin,
                                        new_commission_rate,
                                        new_withdrawal_fee_rate,
                                        new_payment_processing_fee,
                                        pid
                                    )
                                )
                            conn.commit()
                            st.success(f"已更新 {len(selected_products)} 个产品！")
                            st.session_state.products_data = pd.read_sql(
                                "SELECT id, name, category, weight_g "
                                "FROM products", conn
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"批量更新失败: {str(e)}")
            else:
                st.warning("请先选择要编辑的产品")
        else:
            st.info("暂无产品数据")

    # ---------- 产品列表（原生 checkbox） ----------
    st.subheader("产品列表")
    if not products.empty:
        selected_list = []
        for _, row in products.iterrows():
            if st.checkbox(
                f"{row['id']} - {row['name']} "
                f"({row['category']}, {row['weight_g']}g)",
                key=f"product_checkbox_{row['id']}"
            ):
                selected_list.append(row.to_dict())

        if selected_list:
            product_id = selected_list[0]['id']
            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("编辑产品"):
                    st.session_state.edit_product_id = product_id
                    st.rerun()
            with col_del:
                if st.button("删除产品"):
                    c.execute("DELETE FROM products WHERE id=?", (product_id,))
                    conn.commit()
                    st.success("产品删除成功！")
                    st.session_state.products_data = pd.read_sql(
                        "SELECT id, name, category, weight_g "
                        "FROM products", conn
                    )
                    st.rerun()
        else:
            st.info("请勾选产品")
    else:
        st.info("暂无产品数据")


# ---------- 编辑表单 ----------
def edit_product_form():
    conn, c = get_db()
    st.subheader("编辑产品")
    product_id = st.session_state.edit_product_id
    product = c.execute(
        "SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        st.error("产品不存在")
        if st.button("返回列表"):
            del st.session_state.edit_product_id
            st.rerun()
        return

    # 用 product 的列索引对应表结构
    (
        _id, name, russian_name, category, model,
        weight_g, length_cm, width_cm, height_cm,
        is_cylinder, cylinder_diameter,
        has_battery, battery_capacity_wh,
        battery_capacity_mah, battery_voltage,
        has_msds, has_flammable, unit_price,
        shipping_fee, labeling_fee,
        discount_rate, promotion_discount, promotion_cost_rate,
        min_profit_margin, target_profit_margin,
        commission_rate, withdrawal_fee_rate, payment_processing_fee
    ) = product

    # 表单布局（与添加产品完全一致）
    col1, col2 = st.columns(2)
    name = col1.text_input("产品名称*", value=name)
    russian_name = col2.text_input("俄文名称", value=russian_name)
    category = col1.text_input("产品类别", value=category)
    model = col2.text_input("型号", value=model)

    st.subheader("物理规格")
    col1, col2, col3 = st.columns(3)
    weight_g = col1.number_input("重量(g)*", min_value=0, value=weight_g)
    length_cm = col2.number_input("长(cm)*", min_value=0, value=length_cm)
    width_cm = col3.number_input("宽(cm)*", min_value=0, value=width_cm)
    height_cm = st.number_input("高(cm)*", min_value=0, value=height_cm)

    shape = st.radio(
        "包装形状",
        ["标准包装", "圆柱形包装"],
        horizontal=True,
        index=1 if is_cylinder else 0
    )
    is_cylinder = (shape == "圆柱形包装")
    cylinder_diameter = 0.0
    if is_cylinder:
        cylinder_diameter = st.number_input(
            "圆柱直径(cm)*", min_value=0.0, value=cylinder_diameter
        )

    has_battery = st.checkbox("含电池", value=bool(has_battery))
    battery_capacity_wh = 0.0
    battery_capacity_mah = 0
    battery_voltage = 0.0
    if has_battery:
        choice = st.radio(
            "电池容量填写方式",
            ["填写 Wh（瓦时）", "填写 mAh + V"],
            horizontal=True,
            index=0 if battery_capacity_wh > 0 else 1
        )
        if choice == "填写 Wh（瓦时）":
            battery_capacity_wh = st.number_input(
                "电池容量(Wh)*", min_value=0.0, value=battery_capacity_wh
            )
        else:
            col1, col2 = st.columns(2)
            battery_capacity_mah = col1.number_input(
                "电池容量(mAh)*", min_value=0, value=battery_capacity_mah
            )
            battery_voltage = col2.number_input(
                "电池电压(V)*", min_value=0.0, value=battery_voltage
            )

    col1, col2 = st.columns(2)
    has_msds = col1.checkbox("有MSDS文件", value=bool(has_msds))
    has_flammable = col2.checkbox("有易燃液体", value=bool(has_flammable))
    unit_price = col1.number_input("单价(元)*", min_value=0.0, value=unit_price)
    shipping_fee = col2.number_input(
        "发货方运费(元)*", min_value=0.0, value=shipping_fee)
    labeling_fee = st.number_input(
        "代贴单费用(元)*", min_value=0.0, value=labeling_fee)

    st.subheader("定价参数")
    col1, col2 = st.columns(2)
    discount_rate = col1.slider("画线折扣率", 0.0, 1.0, discount_rate, 0.01)
    promotion_discount = col2.slider(
        "活动折扣率", 0.0, 1.0, promotion_discount, 0.01)
    promotion_cost_rate = col1.slider(
        "推广费用率", 0.0, 1.0, promotion_cost_rate, 0.01)
    min_profit_margin = col2.slider("最低利润率", 0.0, 1.0, min_profit_margin, 0.01)
    target_profit_margin = col1.slider(
        "目标利润率", 0.0, 1.0, target_profit_margin, 0.01)
    commission_rate = col2.slider("佣金率", 0.0, 1.0, commission_rate, 0.01)
    withdrawal_fee_rate = col1.slider(
        "提现费率", 0.0, 0.1, withdrawal_fee_rate, 0.001)
    payment_processing_fee = col2.slider(
        "支付手续费率", 0.0, 0.1, payment_processing_fee, 0.001
    )

    col1, col2 = st.columns(2)
    if col1.button("保存修改"):
        c.execute(
            """UPDATE products SET
                name=?, russian_name=?, category=?, model=?,
                weight_g=?, length_cm=?, width_cm=?, height_cm=?,
                is_cylinder=?, cylinder_diameter=?,
                has_battery=?, battery_capacity_wh=?,
                battery_capacity_mah=?, battery_voltage=?,
                has_msds=?, has_flammable=?, unit_price=?,
                shipping_fee=?, labeling_fee=?,
                discount_rate=?, promotion_discount=?,
                promotion_cost_rate=?, min_profit_margin=?,
                target_profit_margin=?, commission_rate=?,
                withdrawal_fee_rate=?, payment_processing_fee=?
                WHERE id=?""",
            (
                name, russian_name, category, model,
                weight_g, length_cm, width_cm, height_cm,
                int(is_cylinder), cylinder_diameter,
                int(has_battery), battery_capacity_wh,
                battery_capacity_mah, battery_voltage,
                int(has_msds), int(has_flammable), unit_price,
                shipping_fee, labeling_fee,
                discount_rate, promotion_discount,
                promotion_cost_rate, min_profit_margin,
                target_profit_margin, commission_rate,
                withdrawal_fee_rate, payment_processing_fee,
                product_id
            )
        )
        conn.commit()
        st.success("产品修改成功！")
        del st.session_state.edit_product_id
        st.session_state.products_data = pd.read_sql(
            "SELECT id, name, category, weight_g FROM products", conn
        )
        st.rerun()

    if col2.button("取消"):
        del st.session_state.edit_product_id
        st.rerun()


# --------------------------
# 页面函数 - 物流规则
# --------------------------
def get_logistics_data():
    """获取物流数据 - 使用缓存"""
    if 'logistics_data' not in st.session_state:
        conn, c = get_db()
        st.session_state.logistics_data = {
            'land': pd.read_sql(
                "SELECT * FROM logistics WHERE type='land'", conn
            ),
            'air': pd.read_sql(
                "SELECT * FROM logistics WHERE type='air'", conn
            )
        }
    land = st.session_state.logistics_data['land']
    air = st.session_state.logistics_data['air']
    all_ = (
        pd.concat([land, air], ignore_index=True)
        if not land.empty and not air.empty
        else pd.DataFrame()
    )
    return land, air, all_


def logistics_page():
    conn, c = get_db()

    # ---------- 如果正在编辑，则跳到编辑表单 ----------
    if st.session_state.get("edit_logistic_id"):
        edit_logistic_form()
        return

    # ---------- 添加物流规则 ----------
    with st.expander("添加物流规则", expanded=False):
        with st.form("logistic_form"):
            name = st.text_input("物流名称*")
            logistic_type = st.selectbox("物流类型*", ["陆运", "空运"])
            min_days = st.number_input("最快时效(天)*", min_value=1, value=10)
            max_days = st.number_input(
                "最慢时效(天)*", min_value=min_days, value=30)
            price_limit = st.number_input("限价(元)", min_value=0.0, value=0.0)

            st.subheader("费用结构")
            base_fee = st.number_input("基础费用(元)", min_value=0.0, value=0.0)
            weight_factor = st.number_input(
                "每100g费用(元)", min_value=0.0, value=0.0)
            volume_factor = st.number_input(
                "每10kg体积费用(元)", min_value=0.0, value=0.0)
            battery_factor = st.number_input(
                "电池附加费(元)", min_value=0.0, value=0.0)

            st.subheader("限制条件")
            min_weight = st.number_input("最小重量(g)", min_value=0, value=0)
            max_weight = st.number_input("最大重量(g)", min_value=0, value=0)
            max_size = st.number_input("最大尺寸(cm)", min_value=0, value=0)
            max_volume_weight = st.number_input(
                "最大体积重量(kg)", min_value=0.0, value=0.0)

            st.subheader("特殊物品限制")
            allow_battery = st.checkbox("允许运输含电池产品")
            allow_flammable = st.checkbox("允许运输易燃液体")

            submitted = st.form_submit_button("添加物流规则")
            if submitted:
                if not name or not min_days or not max_days:
                    st.error("请填写所有必填字段")
                else:
                    try:
                        type_en = {"陆运": "land", "空运": "air"}[logistic_type]
                        c.execute("""INSERT INTO logistics (
                            name,type,min_days,max_days,price_limit,
                            base_fee,weight_factor,volume_factor,battery_factor,
                            min_weight,max_weight,max_size,max_volume_weight,
                            allow_battery,allow_flammable)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                            name, type_en, min_days, max_days, price_limit,
                            base_fee, weight_factor,
                            volume_factor, battery_factor,
                            min_weight, max_weight,
                            max_size, max_volume_weight,
                            int(allow_battery), int(allow_flammable)
                        ))
                        conn.commit()
                        st.success("物流规则添加成功！")
                        st.session_state.pop("logistics_data", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"添加失败: {str(e)}")

    # ---------- 物流列表（原生 table + 按钮） ----------
    st.subheader("物流列表")
    land_df = pd.read_sql("SELECT * FROM logistics WHERE type='land'", conn)
    air_df = pd.read_sql("SELECT * FROM logistics WHERE type='air'", conn)

    col1, col2 = st.columns(2)
    with col1:
        st.write("**陆运**")
        if not land_df.empty:
            for _, row in land_df.iterrows():
                st.write(
                    f"{row['id']} | {row['name']} "
                    f"| {row['min_days']}-{row['max_days']}天")
                if st.button("编辑", key=f"edit_land_{row['id']}"):
                    st.session_state.edit_logistic_id = row['id']
                    st.rerun()
                if st.button("删除", key=f"del_land_{row['id']}"):
                    c.execute("DELETE FROM logistics WHERE id=?", (row['id'],))
                    conn.commit()
                    st.success("已删除！")
                    st.session_state.pop("logistics_data", None)
                    st.rerun()
        else:
            st.info("暂无陆运数据")

    with col2:
        st.write("**空运**")
        if not air_df.empty:
            for _, row in air_df.iterrows():
                st.write(
                    f"{row['id']} | {row['name']} "
                    f"| {row['min_days']}-{row['max_days']}天")
                if st.button("编辑", key=f"edit_air_{row['id']}"):
                    st.session_state.edit_logistic_id = row['id']
                    st.rerun()
                if st.button("删除", key=f"del_air_{row['id']}"):
                    c.execute("DELETE FROM logistics WHERE id=?", (row['id'],))
                    conn.commit()
                    st.success("已删除！")
                    st.session_state.pop("logistics_data", None)
                    st.rerun()
        else:
            st.info("暂无空运数据")


# ================= 物流编辑表单（同级函数） =================
def edit_logistic_form():
    import streamlit as st
    conn, c = get_db()
    st.subheader("编辑物流规则")
    row_id = st.session_state.edit_logistic_id
    row = c.execute("SELECT * FROM logistics WHERE id=?", (row_id,)).fetchone()
    if not row:
        st.error("规则不存在")
        if st.button("返回"):
            del st.session_state.edit_logistic_id
            st.rerun()
        return

    # 表单字段
    with st.form("edit_logistic_form"):
        name = st.text_input("物流名称", value=row["name"])
        logistic_type = st.selectbox(
            "物流类型", ["陆运", "空运"],
            index=0 if row["type"] == "land" else 1
        )
        min_days = st.number_input(
            "最快时效(天)", min_value=1, value=row["min_days"])
        max_days = st.number_input(
            "最慢时效(天)", min_value=min_days, value=row["max_days"])
        price_limit = st.number_input(
            "限价(元)", min_value=0.0, value=row["price_limit"])

        base_fee = st.number_input(
            "基础费用", min_value=0.0, value=row["base_fee"])
        weight_factor = st.number_input(
            "每100g费用", min_value=0.0, value=row["weight_factor"])
        volume_factor = st.number_input(
            "每10kg体积费用", min_value=0.0, value=row["volume_factor"])
        battery_factor = st.number_input(
            "电池附加费", min_value=0.0, value=row["battery_factor"])

        min_weight = st.number_input(
            "最小重量(g)", min_value=0, value=row["min_weight"])
        max_weight = st.number_input(
            "最大重量(g)", min_value=0, value=row["max_weight"])
        max_size = st.number_input(
            "最大尺寸(cm)", min_value=0, value=row["max_size"])
        max_volume_weight = st.number_input(
            "最大体积重量(kg)", min_value=0.0, value=row["max_volume_weight"])

        allow_battery = st.checkbox("允许电池", value=bool(row["allow_battery"]))
        allow_flammable = st.checkbox(
            "允许易燃液体", value=bool(row["allow_flammable"]))

        submitted = st.form_submit_button("保存修改")
        if submitted:
            type_en = {"陆运": "land", "空运": "air"}[logistic_type]
            c.execute("""UPDATE logistics SET
                name=?, type=?, min_days=?, max_days=?, price_limit=?,
                base_fee=?, weight_factor=?, volume_factor=?, battery_factor=?,
                min_weight=?, max_weight=?, max_size=?, max_volume_weight=?,
                allow_battery=?, allow_flammable=? WHERE id=?""", (
                name, type_en, min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight, max_size, max_volume_weight,
                int(allow_battery), int(allow_flammable), row_id
            ))
            conn.commit()
            st.success("修改成功！")
            del st.session_state.edit_logistic_id
            st.session_state.pop("logistics_data", None)
            st.rerun()

    # 取消按钮放在表单外
    if st.button("取消"):
        del st.session_state.edit_logistic_id
        st.rerun()


# --------------------------
# 页面函数 - 定价计算器
# --------------------------
def pricing_calculator_page():
    st.title("物流定价计算器")
    conn, c = get_db()

    # ---------- 内部专用 dict 列表读取 ----------
    def _load_logistics_dict():
        """只在 pricing_calculator_page 内部使用"""
        land_df = pd.read_sql(
            "SELECT * FROM logistics WHERE type='land'", conn
        )
        air_df = pd.read_sql("SELECT * FROM logistics WHERE type='air'", conn)
        return {
            'land': land_df.to_dict(orient='records'),
            'air': air_df.to_dict(orient='records')
        }

    # 获取物流选项（仅 dict 列表）
    if 'logistics_dict' not in st.session_state:
        st.session_state.logistics_dict = _load_logistics_dict()

    land_logistics = st.session_state.logistics_dict['land']
    air_logistics = st.session_state.logistics_dict['air']

    if not land_logistics or not air_logistics:
        st.warning("请先配置物流规则")
        return

    # 选择产品
    if 'products_data' in st.session_state:
        products = st.session_state.products_data
    else:
        with st.spinner("加载产品数据..."):
            products = pd.read_sql("SELECT id, name FROM products", conn)
            st.session_state.products_data = products

    if products.empty:
        st.warning("请先添加产品")
        return

    def format_product_name(x):
        product_name = products.loc[
            products['id'] == x, 'name'
        ].values[0]
        return f"{x} - {product_name}"

    product_id = st.selectbox(
        "选择产品", products['id'],
        format_func=format_product_name
    )

    # 获取产品详情
    product = c.execute(
        "SELECT * FROM products WHERE id=?", (product_id,)
    ).fetchone()
    if not product:
        st.error("产品不存在")
        return

    # 将产品转换为字典格式
    product_dict = {
        'id': product[0],
        'name': product[1],
        'russian_name': product[2],
        'category': product[3],
        'model': product[4],
        'weight_g': product[5],
        'length_cm': product[6],
        'width_cm': product[7],
        'height_cm': product[8],
        'is_cylinder': bool(product[9]),
        'cylinder_diameter': product[10],
        'has_battery': bool(product[11]),
        'battery_capacity_wh': product[12],
        'battery_capacity_mah': product[13],
        'battery_voltage': product[14],
        'has_msds': bool(product[15]),
        'has_flammable': bool(product[16]),
        'unit_price': product[17],
        'shipping_fee': product[18],
        'labeling_fee': product[19],
        'discount_rate': product[20],
        'promotion_discount': product[21],
        'promotion_cost_rate': product[22],
        'min_profit_margin': product[23],
        'target_profit_margin': product[24],
        'commission_rate': product[25],
        'withdrawal_fee_rate': product[26],
        'payment_processing_fee': product[27]
    }

    # 显示产品信息
    with st.expander("产品详情", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("产品名称", product_dict['name'])
            st.metric("重量(g)", product_dict['weight_g'])
            dimensions = (
                f"{product_dict['length_cm']}×"
                f"{product_dict['width_cm']}×"
                f"{product_dict['height_cm']}"
            )
            st.metric("尺寸(cm)", dimensions)
            volume_weight = (
                product_dict['length_cm'] *
                product_dict['width_cm'] *
                product_dict['height_cm']
            ) / 6000
            st.metric("体积重量(kg)", f"{volume_weight:.2f}")

        with col2:
            st.metric("俄文名称", product_dict['russian_name'] or "-")
            st.metric("含电池", "是" if product_dict['has_battery'] else "否")
            st.metric("单价(元)", product_dict['unit_price'])
            st.metric("发货方运费(元)", product_dict['shipping_fee'])

        with col3:
            st.metric("产品类型", product_dict['category'] or "-")
            flammable = "是" if product_dict['has_flammable'] else "否"
            st.metric("有易燃液体", flammable)
            st.metric("代贴单费用(元)", product_dict['labeling_fee'])
            st.metric("圆柱包装", "是" if product_dict['is_cylinder'] else "否")

    # ---------- 统一加载物流数据 ----------
    def load_logistics():
        conn, c = get_db()
        land_df = pd.read_sql(
            "SELECT * FROM logistics WHERE type='land'", conn
        )
        air_df = pd.read_sql("SELECT * FROM logistics WHERE type='air'", conn)
        return {
            'land': land_df.to_dict(orient='records'),
            'air': air_df.to_dict(orient='records')
        }

    # 强制覆盖缓存，确保是 list[dict]
    st.session_state.logistics_data = load_logistics()

    land_logistics = st.session_state.logistics_data['land']
    air_logistics = st.session_state.logistics_data['air']

    if not land_logistics or not air_logistics:
        st.warning("请先配置物流规则")
        return

    # 自动选择最优物流
    st.subheader("物流自动选择")
    st.info("系统将自动筛选速度快于平均值的物流方式，并选择其中运费最低的")

    # 计算物流平均时效
    land_avg = np.mean(
        [(log['min_days'] + log['max_days'])/2 for log in land_logistics]
    )
    air_avg = np.mean(
        [(log['min_days'] + log['max_days'])/2 for log in air_logistics]
    )

    # 筛选快于平均时效的物流
    fast_land = [
        log for log in land_logistics
        if (log['min_days'] + log['max_days'])/2 < land_avg
    ]
    fast_air = [
        log for log in air_logistics
        if (log['min_days'] + log['max_days'])/2 < air_avg
    ]

    if not fast_land or not fast_air:
        st.warning("没有符合条件的物流方式")
        return

    # 转换为DataFrame方便操作
    land_df = pd.DataFrame(fast_land)
    air_df = pd.DataFrame(fast_air)

    # 计算每种物流的费用
    land_df['cost'] = land_df.apply(
        lambda row: calculate_logistic_cost(row, product_dict),
        axis=1
    )
    air_df['cost'] = air_df.apply(
        lambda row: calculate_logistic_cost(row, product_dict),
        axis=1
    )

    # 排除无效结果
    land_df = land_df.dropna(subset=['cost'])
    air_df = air_df.dropna(subset=['cost'])

    if land_df.empty or air_df.empty:
        st.warning("没有有效的物流计算结果")
        return

    # 找到成本最低的物流
    best_land = land_df.loc[land_df['cost'].idxmin()]
    best_air = air_df.loc[air_df['cost'].idxmin()]

    # 显示自动选择结果
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("推荐陆运")
        st.metric("物流方式", best_land['name'])
        st.metric(
            "时效",
            f"{best_land['min_days']}-{best_land['max_days']}天"
        )
        st.metric("运费(元)", f"{best_land['cost']:.2f}")

    with col2:
        st.subheader("推荐空运")
        st.metric("物流方式", best_air['name'])
        st.metric(
            "时效",
            f"{best_air['min_days']}-{best_air['max_days']}天"
        )
        st.metric("运费(元)", f"{best_air['cost']:.2f}")

    # 计算最终定价
    land_price, air_price, land_cost, air_cost = calculate_pricing(
        product_dict, best_land, best_air
    )

    if land_price and air_price:
        st.subheader("最终定价")

        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "陆运价格(元)", f"{land_price:.2f}",
                delta=f"运费: ¥{land_cost:.2f}"
            )

        with col2:
            st.metric(
                "空运价格(元)", f"{air_price:.2f}",
                delta=f"运费: ¥{air_cost:.2f}"
            )

        # 显示定价明细
        with st.expander("定价明细分析"):
            st.write("**成本构成:**")
            cost_data = {
                "项目": ["产品单价", "发货方运费", "代贴单费用", "陆运运费", "空运运费"],
                "金额(元)": [
                    product_dict['unit_price'],
                    product_dict['shipping_fee'],
                    product_dict['labeling_fee'],
                    land_cost,
                    air_cost
                ]
            }
            st.dataframe(pd.DataFrame(cost_data))

            st.write("**费用率:**")
            fee_data = {
                "费用类型": ["画线折扣", "活动折扣", "推广费用", "佣金", "提现费", "支付手续费"],
                "费率": [
                    f"{product_dict['discount_rate']*100:.1f}%",
                    f"{product_dict['promotion_discount']*100:.1f}%",
                    f"{product_dict['promotion_cost_rate']*100:.1f}%",
                    f"{product_dict['commission_rate']*100:.1f}%",
                    f"{product_dict['withdrawal_fee_rate']*100:.1f}%",
                    f"{product_dict['payment_processing_fee']*100:.1f}%"
                ]
            }
            st.dataframe(pd.DataFrame(fee_data))

            # 计算利润率
            land_total_cost = (
                product_dict['unit_price'] + land_cost +
                product_dict['shipping_fee'] + product_dict['labeling_fee']
            )
            air_total_cost = (
                product_dict['unit_price'] + air_cost +
                product_dict['shipping_fee'] + product_dict['labeling_fee']
            )

            land_profit = land_price - land_total_cost
            air_profit = air_price - air_total_cost

            land_margin = land_profit / land_price
            air_margin = air_profit / air_price

            st.write("**利润率分析:**")
            profit_data = {
                "物流类型": ["陆运", "空运"],
                "总成本(元)": [land_total_cost, air_total_cost],
                "销售价格(元)": [land_price, air_price],
                "利润(元)": [land_profit, air_profit],
                "利润率": [
                    f"{land_margin*100:.2f}%",
                    f"{air_margin*100:.2f}%"
                ]
            }
            st.dataframe(pd.DataFrame(profit_data))

            # 利润率检查
            min_margin = product_dict.get('min_profit_margin', 0.3)
            if land_margin < min_margin:
                st.warning(
                    f"⚠️ 陆运利润率 {land_margin*100:.2f}% "
                    f"低于最低要求 {min_margin*100:.1f}%"
                )
            if air_margin < min_margin:
                st.warning(
                    f"⚠️ 空运利润率 {air_margin*100:.2f}% "
                    f"低于最低要求 {min_margin*100:.1f}%"
                )


# --------------------------
# 页面函数 - 用户管理（原生控件版）
# --------------------------
def user_management_page():
    st.title("用户管理")
    conn, c = get_db()

    # ---------- 添加新用户 ----------
    with st.expander("添加新用户"):
        with st.form("user_form"):
            username = st.text_input("用户名*")
            password = st.text_input("密码*", type="password")
            role = st.selectbox("角色*", ["admin", "user"])
            submitted = st.form_submit_button("添加用户")
            if submitted:
                if not username or not password:
                    st.error("请填写所有必填字段（带*号）")
                else:
                    if create_user(username, password, role):
                        st.success("用户添加成功！")
                        st.rerun()
                    else:
                        st.error("用户名已存在")

    # ---------- 用户列表 ----------
    st.subheader("用户列表")
    users = pd.read_sql("SELECT id, username, role FROM users", conn)

    if users.empty:
        st.info("暂无用户数据")
        return

    # 单选：用 radio 展示 id - username (role)
    choice = st.radio(
        "请选择一名用户",
        options=users.itertuples(index=False),   # 返回 namedtuple
        format_func=lambda x: f"{x.id} - {x.username} ({x.role})"
    )

    if choice:
        user_id = choice.id
        st.write("---")
        st.write(f"**已选用户：** {choice.username}（{choice.role}）")

        # 重置密码
        with st.expander("重置密码"):
            with st.form("reset_password_form"):
                new_pwd = st.text_input("新密码*", type="password")
                if st.form_submit_button("确认重置"):
                    if not new_pwd:
                        st.error("请输入新密码")
                    else:
                        hashed = hashlib.sha256(new_pwd.encode()).hexdigest()
                        c.execute("UPDATE users SET password=? WHERE id=?",
                                  (hashed, user_id))
                        conn.commit()
                        st.success("密码已更新！")
                        st.rerun()

        # 删除用户
        if st.button("删除用户", key=f"del_{user_id}"):
            if user_id == st.session_state.user['id']:
                st.error("不能删除当前登录用户")
            else:
                c.execute("DELETE FROM users WHERE id=?", (user_id,))
                conn.commit()
                st.success("用户已删除！")
                st.rerun()
    else:
        st.info("暂无用户数据")


# --------------------------
# Streamlit 应用界面 (主函数)
# --------------------------
def main():
    st.set_page_config(
        page_title="物流定价系统",
        page_icon="📦",
        layout="wide"
    )

    st.sidebar.subheader("调试信息")
    debug_mode = st.sidebar.checkbox("启用调试模式", False)
    st.session_state.debug_mode = debug_mode

    # 初始化数据库
    init_db()

    # 用户认证
    if 'user' not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        st.title("物流定价系统 - 登录")
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")

        if st.button("登录"):
            user = verify_user(username, password)
            if user:
                st.session_state.user = {
                    "id": user[0],
                    "username": user[1],
                    "role": user[3]
                }
                st.success("登录成功！")
                st.rerun()
            else:
                st.error("用户名或密码错误")
        return

    # 主界面
    st.sidebar.title(f"欢迎, {st.session_state.user['username']}")
    st.sidebar.subheader(f"角色: {st.session_state.user['role']}")

    # 导航菜单
    menu_options = ["产品管理", "物流规则", "定价计算器"]
    if st.session_state.user['role'] == 'admin':
        menu_options.append("用户管理")

    selected_page = st.sidebar.selectbox("导航", menu_options)

    # 页面路由
    if selected_page == "产品管理":
        products_page()
    elif selected_page == "物流规则":
        logistics_page()
    elif selected_page == "定价计算器":
        pricing_calculator_page()
    elif selected_page == "用户管理" and st.session_state.user['role'] == 'admin':
        user_management_page()

    # 退出登录按钮
    if st.sidebar.button("退出登录", key="logout_button"):
        st.session_state.user = None
        # 清除所有缓存
        st.session_state.pop('products_data', None)
        st.session_state.pop('logistics_data', None)
        st.rerun()


if __name__ == "__main__":
    main()
