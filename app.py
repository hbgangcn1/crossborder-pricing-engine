# app.py
import hashlib
import math
import numpy as np
import pandas as pd
import re
import sqlite3
import streamlit as st
import threading
import time
import os

# -------------------------- 线程局部存储
thread_local = threading.local()


# -------------------------- 汇率后台线程
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
                cls._update_thread = threading.Thread(
                    target=cls._instance._background_update,
                    daemon=True
                )
                cls._update_thread.start()
        return cls._instance

    def _background_update(self):
        while True:
            try:
                if time.time() - self.last_updated >= 3600:
                    self.exchange_rate = 11.5  # 模拟值
                    self.last_updated = time.time()
                    if st.session_state.get('debug_mode', False):
                        st.info("汇率后台更新成功！")
            except Exception:
                pass
            time.sleep(60)

    def get_exchange_rate(self):
        return self.exchange_rate


# -------------------------- 数据库连接（绝对路径）
@st.cache_resource
def get_db():
    db_path = os.path.join(os.path.dirname(__file__), "pricing_system.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


# -------------------------- 升级表结构：增加 user_id
def _upgrade_table_user_id(table: str):
    conn, c = get_db()
    c.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in c.fetchall()]
    if "user_id" not in cols:
        c.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
        if table == "products":
            c.execute("""
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT,
                    russian_name TEXT,
                    category TEXT,
                    model TEXT,
                    weight_g INTEGER,
                    length_cm INTEGER,
                    width_cm INTEGER,
                    height_cm INTEGER,
                    is_cylinder INTEGER,
                    cylinder_diameter REAL,
                    has_battery INTEGER,
                    battery_capacity_wh REAL,
                    battery_capacity_mah INTEGER,
                    battery_voltage REAL,
                    has_msds INTEGER,
                    has_flammable INTEGER,
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
                    payment_processing_fee REAL DEFAULT 0.013
                )
            """)
            c.execute("""
                INSERT INTO products (
                    user_id, name, russian_name, category, model,
                    weight_g, length_cm, width_cm, height_cm,
                    is_cylinder, cylinder_diameter,
                    has_battery, battery_capacity_wh,
                    battery_capacity_mah, battery_voltage,
                    has_msds, has_flammable,
                    unit_price, shipping_fee, labeling_fee,
                    discount_rate, promotion_discount,
                    promotion_cost_rate, min_profit_margin,
                    target_profit_margin, commission_rate,
                    withdrawal_fee_rate, payment_processing_fee
                )
                SELECT
                    (SELECT id FROM users WHERE role='admin' LIMIT 1),
                    name, russian_name, category, model,
                    weight_g, length_cm, width_cm, height_cm,
                    is_cylinder, cylinder_diameter,
                    has_battery, battery_capacity_wh,
                    battery_capacity_mah, battery_voltage,
                    has_msds, has_flammable,
                    unit_price, shipping_fee, labeling_fee,
                    discount_rate, promotion_discount,
                    promotion_cost_rate, min_profit_margin,
                    target_profit_margin, commission_rate,
                    withdrawal_fee_rate, payment_processing_fee
                FROM products_old
            """)
        elif table == "logistics":
            c.execute("""
                CREATE TABLE logistics (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
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
                    allow_battery INTEGER,
                    allow_flammable INTEGER
                )
            """)
            c.execute("""
                INSERT INTO logistics (
                    user_id, name, type, min_days, max_days, price_limit,
                    base_fee, weight_factor, volume_factor, battery_factor,
                    min_weight, max_weight, max_size, max_volume_weight,
                    allow_battery, allow_flammable
                )
                SELECT
                    (SELECT id FROM users WHERE role='admin' LIMIT 1),
                    name, type, min_days, max_days, price_limit,
                    base_fee, weight_factor, volume_factor, battery_factor,
                    min_weight, max_weight, max_size, max_volume_weight,
                    allow_battery, allow_flammable
                FROM logistics_old
            """)
        c.execute(f"DROP TABLE {table}_old")
        conn.commit()


# -------------------------- 初始化数据库
def init_db():
    conn, c = get_db()

    # 1. 先完整创建三张表
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            email TEXT UNIQUE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT,
            russian_name TEXT,
            category TEXT,
            model TEXT,
            weight_g INTEGER,
            length_cm INTEGER,
            width_cm INTEGER,
            height_cm INTEGER,
            is_cylinder INTEGER,
            cylinder_diameter REAL,
            has_battery INTEGER,
            battery_capacity_wh REAL,
            battery_capacity_mah INTEGER,
            battery_voltage REAL,
            has_msds INTEGER,
            has_flammable INTEGER,
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
            payment_processing_fee REAL DEFAULT 0.013
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS logistics (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
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
            allow_battery INTEGER,
            allow_flammable INTEGER
        )
    """)
    conn.commit()

    # 2. 升级旧数据（如存在）
    _upgrade_table_user_id("products")
    _upgrade_table_user_id("logistics")

    # 3. 初始管理员
    if not verify_user("admin", "admin123"):
        create_user("admin", "admin123", "admin")


# -------------------------- 认证
def create_user(username, password, role='user', email=None):
    conn, c = get_db()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute(
            "INSERT INTO users (username, password, role, email) "
            "VALUES (?, ?, ?, ?)",
            (username, hashed, role, email)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(identifier, password):
    conn, c = get_db()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    user = c.execute(
        "SELECT * FROM users "
        "WHERE (username = ? OR email = ?) AND password = ?",
        (identifier, identifier, hashed)
    ).fetchone()
    return dict(user) if user else None


# -------------------------- 辅助
def current_user_id():
    return st.session_state.user['id']


# -------------------------- 物流计算
def calculate_logistic_cost(logistic, product):
    try:
        min_w = logistic.get('min_weight', 0)
        max_w = logistic.get('max_weight', 10**9)
        w = product.get('weight_g', 0)
        if w < min_w or w > max_w:
            return None

        max_sz = logistic.get('max_size', 10**9)
        for k in ('length_cm', 'width_cm', 'height_cm'):
            if product.get(k, 0) > max_sz:
                return None

        vol_w = (
            product['length_cm'] *
            product['width_cm'] *
            product['height_cm']
        ) / 6000
        max_vol = logistic.get('max_volume_weight', 10**9)
        if vol_w > max_vol:
            return None

        if product.get('has_battery') and not logistic.get('allow_battery'):
            return None
        if (
            product.get('has_flammable') and
            not logistic.get('allow_flammable')
        ):
            return None

        cost = logistic.get('base_fee', 0)
        if logistic.get('weight_factor'):
            cost += logistic['weight_factor'] * math.ceil(w / 100)
        if logistic.get('volume_factor'):
            cost += logistic['volume_factor'] * math.ceil(vol_w * 10)
        if product.get('has_battery') and logistic.get('battery_factor'):
            cost += logistic['battery_factor']
        return cost
    except Exception as e:
        st.error(f"物流费用计算错误: {e}")
        return None


# -------------------------- 定价
def calculate_pricing(product, land_logistics, air_logistics):
    try:
        unit_price = product['unit_price']
        shipping_fee = product['shipping_fee']
        labeling_fee = product['labeling_fee']
        rate = ExchangeRateService().get_exchange_rate()

        def _cost_and_filter(logistics):
            res = []
            for log in logistics:
                cost = calculate_logistic_cost(log, product)
                if cost is None:
                    continue
                limit = log.get('price_limit') or 0
                rough = (
                    (
                        unit_price * 1.01 + labeling_fee +
                        shipping_fee + cost + 15 * rate
                    )
                    /
                    (
                        (1 - 0.15) * (1 - 0.05) * (1 - 0.175) *
                        (1 - 0.01) * (1 - 0.013)
                    )
                )
                if limit == 0 or rough <= limit:
                    res.append((log, cost))
            return res

        land_candidates = _cost_and_filter(land_logistics)
        air_candidates = _cost_and_filter(air_logistics)
        if not land_candidates or not air_candidates:
            return None, None, None, None

        best_land, land_cost = min(land_candidates, key=lambda x: x[1])
        best_air, air_cost = min(air_candidates, key=lambda x: x[1])

        def final_price(cost):
            return round(
                (unit_price * (1 + product['withdrawal_fee_rate']) +
                 labeling_fee + shipping_fee + cost + 15 * rate) /
                ((1 - product['discount_rate']) *
                 (1 - product['promotion_discount']) *
                 (1 - product['commission_rate']) *
                 (1 - product['withdrawal_fee_rate']) *
                 (1 - product['payment_processing_fee'])), 2
            )

        land_price = final_price(land_cost)
        air_price = final_price(air_cost)

        return land_price, air_price, land_cost, air_cost
    except Exception as e:
        st.error(f"定价计算错误: {e}")
        return None, None, None, None


# -------------------------- 页面：产品管理
def products_page():
    conn, c = get_db()
    uid = current_user_id()

    if st.session_state.get("edit_product_id"):
        edit_product_form()
        return

    # 缓存产品表
    products = pd.read_sql(
        "SELECT id, name, category, weight_g "
        "FROM products "
        "WHERE user_id = ?",
        conn, params=(uid,)
    )

    # 添加/编辑产品
    with st.expander("添加新产品", expanded=True):
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
        cylinder_diameter = 0.0
        if is_cylinder:
            cylinder_diameter = st.number_input(
                "圆柱直径(cm)*",
                min_value=0.0,
                value=0.0
            )

        has_battery = st.checkbox("含电池")
        battery_capacity_wh = 0.0
        battery_capacity_mah = 0
        battery_voltage = 0.0
        if has_battery:
            choice = st.radio(
                "电池容量填写方式",
                ["填写 Wh（瓦时）", "填写 mAh + V"],
                horizontal=True
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
                    "INSERT INTO products ("
                    "user_id, name, russian_name, category, model, "
                    "weight_g, length_cm, width_cm, height_cm, "
                    "is_cylinder, cylinder_diameter, has_battery, "
                    "battery_capacity_wh, battery_capacity_mah, "
                    "battery_voltage, has_msds, has_flammable, "
                    "unit_price, shipping_fee, labeling_fee, "
                    "min_profit_margin, target_profit_margin, "
                    "commission_rate, withdrawal_fee_rate, "
                    "payment_processing_fee) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                    "?,?,?,?,?,?,?,?,?)",
                    (
                        uid, name, russian_name, category, model,
                        weight_g, length_cm, width_cm, height_cm,
                        int(is_cylinder), cylinder_diameter,
                        int(has_battery), battery_capacity_wh,
                        battery_capacity_mah, battery_voltage,
                        int(has_msds), int(has_flammable), unit_price,
                        shipping_fee, labeling_fee, discount_rate,
                        promotion_discount, promotion_cost_rate,
                        min_profit_margin, target_profit_margin,
                        commission_rate, withdrawal_fee_rate,
                        payment_processing_fee
                    )
                )
                conn.commit()
                st.success("产品添加成功！")
                st.session_state.products_data = pd.read_sql(
                    "SELECT id, name, category, weight_g "
                    "FROM products "
                    "WHERE user_id = ?",
                    conn, params=(uid,)
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
                key=f"product_checkbox_{row['id']}"
            ):
                selected_list.append(row.to_dict())
        if selected_list:
            product_id = selected_list[0]['id']
            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("编辑产品", key=f"edit_btn_{product_id}"):
                    st.session_state.edit_product_id = product_id
                    st.rerun()
            with col_del:
                if st.button("删除产品", key=f"del_btn_{product_id}"):
                    c.execute(
                        "DELETE FROM products WHERE id=? AND user_id=?",
                        (product_id, uid)
                    )
                    conn.commit()
                    st.session_state.products_data = pd.read_sql(
                        "SELECT id, name, category, weight_g "
                        "FROM products "
                        "WHERE user_id = ?",
                        conn, params=(uid,)
                    )
                    st.rerun()
    else:
        st.info("暂无产品数据")


# ---------- 编辑表单
def edit_product_form():
    conn, c = get_db()
    uid = current_user_id()
    product_id = st.session_state.edit_product_id
    product = c.execute(
        "SELECT * FROM products WHERE id=? AND user_id=?", (product_id, uid)
    ).fetchone()
    if not product:
        st.error("产品不存在或无权编辑")
        if st.button("返回列表"):
            del st.session_state.edit_product_id
            st.rerun()
        return

    fields = list(product.keys())
    vals = dict(zip(fields, product))

    st.subheader("编辑产品")
    with st.form("edit_product_form"):
        col1, col2 = st.columns(2)
        name = col1.text_input("产品名称*", value=vals['name'])
        russian_name = col2.text_input(
            "俄文名称",
            value=vals['russian_name'] or ""
        )
        category = col1.text_input("产品类别", value=vals['category'] or "")
        model = col2.text_input("型号", value=vals['model'] or "")

        st.subheader("物理规格")
        col1, col2, col3 = st.columns(3)
        weight_g = col1.number_input("重量(g)*", value=vals['weight_g'])
        length_cm = col2.number_input("长(cm)*", value=vals['length_cm'])
        width_cm = col3.number_input("宽(cm)*", value=vals['width_cm'])
        height_cm = st.number_input("高(cm)*", value=vals['height_cm'])

        shape = st.radio(
            "包装形状",
            ["标准包装", "圆柱形包装"],
            index=1 if vals['is_cylinder'] else 0,
            horizontal=True
        )
        is_cylinder = (shape == "圆柱形包装")
        cylinder_diameter = 0.0
        if is_cylinder:
            cylinder_diameter = st.number_input(
                "圆柱直径(cm)*",
                value=vals['cylinder_diameter']
            )

        has_battery = st.checkbox("含电池", value=bool(vals['has_battery']))
        battery_capacity_wh = 0.0
        battery_capacity_mah = 0
        battery_voltage = 0.0
        if has_battery:
            choice = st.radio(
                "电池容量填写方式",
                ["填写 Wh（瓦时）", "填写 mAh + V"],
                index=0 if vals['battery_capacity_wh'] > 0 else 1,
                horizontal=True
            )
            if choice == "填写 Wh（瓦时）":
                battery_capacity_wh = st.number_input(
                    "电池容量(Wh)*",
                    value=vals['battery_capacity_wh']
                )
            else:
                col1, col2 = st.columns(2)
                battery_capacity_mah = col1.number_input(
                    "电池容量(mAh)*",
                    value=vals['battery_capacity_mah']
                )
                battery_voltage = col2.number_input(
                    "电池电压(V)*",
                    value=vals['battery_voltage']
                )

        col1, col2 = st.columns(2)
        has_msds = col1.checkbox("有MSDS文件", value=bool(vals['has_msds']))
        has_flammable = col2.checkbox(
            "有易燃液体",
            value=bool(vals['has_flammable'])
        )
        unit_price = col1.number_input("单价(元)*", value=vals['unit_price'])
        shipping_fee = col2.number_input(
            "发货方运费(元)*",
            value=vals['shipping_fee']
        )
        labeling_fee = st.number_input("代贴单费用(元)*", value=vals['labeling_fee'])

        st.subheader("定价参数")
        col1, col2 = st.columns(2)
        discount_rate = col1.slider(
            "画线折扣率", 0.0, 1.0, vals['discount_rate'], 0.01
        )
        promotion_discount = col2.slider(
            "活动折扣率", 0.0, 1.0, vals['promotion_discount'], 0.01
        )
        promotion_cost_rate = col1.slider(
            "推广费用率", 0.0, 1.0, vals['promotion_cost_rate'], 0.01
        )
        min_profit_margin = col2.slider(
            "最低利润率", 0.0, 1.0, vals['min_profit_margin'], 0.01
        )
        target_profit_margin = col1.slider(
            "目标利润率", 0.0, 1.0, vals['target_profit_margin'], 0.01
        )
        commission_rate = col2.slider(
            "佣金率", 0.0, 1.0, vals['commission_rate'], 0.01
        )
        withdrawal_fee_rate = col1.slider(
            "提现费率", 0.0, 0.1, vals['withdrawal_fee_rate'], 0.001
        )
        payment_processing_fee = col2.slider(
            "支付手续费率", 0.0, 0.1, vals['payment_processing_fee'], 0.001
        )

        if st.form_submit_button("保存修改"):
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
                WHERE id=? AND user_id=?""",
                (name, russian_name, category, model,
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
                 product_id, uid)
            )
            conn.commit()
            st.success("产品修改成功！")
            del st.session_state.edit_product_id
            st.session_state.products_data = pd.read_sql(
                "SELECT id, name, category, weight_g "
                "FROM products "
                "WHERE user_id = ?",
                conn, params=(uid,)
            )
            st.rerun()

    if st.button("取消", key="edit_cancel"):
        del st.session_state.edit_product_id
        st.rerun()


# -------------------------- 页面：物流规则
def logistics_page():
    conn, c = get_db()
    uid = current_user_id()

    if st.session_state.get("edit_logistic_id"):
        edit_logistic_form()
        return

    # 添加物流规则
    with st.expander("添加物流规则", expanded=True):
        with st.form("add_logistic_form"):
            name = st.text_input("物流名称*")
            logistic_type = st.selectbox("物流类型*", ["陆运", "空运"])
            min_days = st.number_input("最快时效(天)*", min_value=1, value=10)
            max_days = st.number_input(
                "最慢时效(天)*",
                min_value=min_days,
                value=30
            )
            price_limit = st.number_input("限价(元)", min_value=0.0, value=0.0)

            st.subheader("费用结构")
            base_fee = st.number_input("基础费用(元)", value=0.0)
            weight_factor = st.number_input("每100g费用(元)", value=0.0)
            volume_factor = st.number_input("每10kg体积费用(元)", value=0.0)
            battery_factor = st.number_input("电池附加费(元)", value=0.0)

            st.subheader("限制条件")
            min_weight = st.number_input("最小重量(g)", value=0)
            max_weight = st.number_input("最大重量(g)", value=0)
            max_size = st.number_input("最大尺寸(cm)", value=0)
            max_volume_weight = st.number_input("最大体积重量(kg)", value=0.0)

            st.subheader("特殊物品限制")
            allow_battery = st.checkbox("允许运输含电池产品")
            allow_flammable = st.checkbox("允许运输易燃液体")

            if st.form_submit_button("添加物流规则"):
                if not name or not min_days or not max_days:
                    st.error("请填写所有必填字段")
                else:
                    type_en = {"陆运": "land", "空运": "air"}[logistic_type]
                    c.execute(
                        "INSERT INTO logistics ("
                        "user_id, name, type, min_days, max_days, "
                        "price_limit, base_fee, weight_factor, "
                        "volume_factor, battery_factor, min_weight, "
                        "max_weight, max_size, max_volume_weight, "
                        "allow_battery, allow_flammable) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            uid, name, type_en, min_days, max_days,
                            price_limit, base_fee, weight_factor,
                            volume_factor, battery_factor,
                            min_weight, max_weight, max_size,
                            max_volume_weight,
                            int(allow_battery), int(allow_flammable)
                        )
                    )
                    conn.commit()
                    st.success("物流规则添加成功！")
                    st.rerun()

    # 物流列表
    st.subheader("物流列表")
    land_df = pd.read_sql(
        "SELECT * FROM logistics "
        "WHERE type='land' AND user_id = ?",
        conn, params=(uid,)
    )
    air_df = pd.read_sql(
        "SELECT * FROM logistics "
        "WHERE type='air' AND user_id = ?",
        conn, params=(uid,)
    )

    left, right = st.columns(2)
    with left:
        st.write("**陆运**")
        if not land_df.empty:
            for _, row in land_df.iterrows():
                st.write(
                    f"{row['id']} | {row['name']} | "
                    f"{row['min_days']}-{row['max_days']}天"
                )
                if st.button("编辑", key=f"edit_land_{row['id']}"):
                    st.session_state.edit_logistic_id = row['id']
                    st.rerun()
                if st.button("删除", key=f"del_land_{row['id']}"):
                    c.execute(
                        "DELETE FROM logistics WHERE id=? AND user_id=?",
                        (row['id'], uid)
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
                    f"{row['min_days']}-{row['max_days']}天"
                )
                if st.button("编辑", key=f"edit_air_{row['id']}"):
                    st.session_state.edit_logistic_id = row['id']
                    st.rerun()
                if st.button("删除", key=f"del_air_{row['id']}"):
                    c.execute(
                        "DELETE FROM logistics WHERE id=? AND user_id=?",
                        (row['id'], uid)
                    )
                    conn.commit()
                    st.rerun()
        else:
            st.info("暂无空运数据")


# ---------- 物流编辑表单
def edit_logistic_form():
    conn, c = get_db()
    uid = current_user_id()
    lid = st.session_state.edit_logistic_id
    row = c.execute(
        "SELECT * FROM logistics WHERE id=? AND user_id=?", (lid, uid)
    ).fetchone()
    if not row:
        st.error("规则不存在或无权编辑")
        if st.button("返回"):
            del st.session_state.edit_logistic_id
            st.rerun()
        return

    vals = dict(zip(row.keys(), row))
    with st.form("edit_logistic_form"):
        name = st.text_input("物流名称", value=vals['name'])
        typ = st.selectbox("物流类型", ["陆运", "空运"],
                           index=0 if vals['type'] == 'land' else 1)
        min_days = st.number_input("最快时效(天)", value=vals['min_days'])
        max_days = st.number_input("最慢时效(天)", value=vals['max_days'])
        price_limit = st.number_input("限价(元)", value=vals['price_limit'])

        base_fee = st.number_input("基础费用", value=vals['base_fee'])
        weight_factor = st.number_input("每100g费用", value=vals['weight_factor'])
        volume_factor = st.number_input(
            "每10kg体积费用",
            value=vals['volume_factor']
        )
        battery_factor = st.number_input("电池附加费", value=vals['battery_factor'])

        min_weight = st.number_input("最小重量(g)", value=vals['min_weight'])
        max_weight = st.number_input("最大重量(g)", value=vals['max_weight'])
        max_size = st.number_input("最大尺寸(cm)", value=vals['max_size'])
        max_volume_weight = st.number_input(
            "最大体积重量(kg)",
            value=vals['max_volume_weight']
        )

        allow_battery = st.checkbox("允许电池", value=bool(vals['allow_battery']))
        allow_flammable = st.checkbox(
            "允许易燃液体",
            value=bool(vals['allow_flammable'])
        )

        if st.form_submit_button("保存修改"):
            c.execute("""
                UPDATE logistics SET
                    name=?, type=?, min_days=?, max_days=?, price_limit=?,
                    base_fee=?, weight_factor=?, volume_factor=?,
                    battery_factor=?, min_weight=?, max_weight=?,
                    max_size=?, max_volume_weight=?,
                    allow_battery=?, allow_flammable=?
                WHERE id=? AND user_id=?
            """, (
                name, {"陆运": "land", "空运": "air"}[typ],
                min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight, max_size, max_volume_weight,
                int(allow_battery), int(allow_flammable),
                lid, uid
            ))
            conn.commit()
            st.success("修改成功！")
            del st.session_state.edit_logistic_id
            st.rerun()

    if st.button("取消"):
        del st.session_state.edit_logistic_id
        st.rerun()


# -------------------------- 页面：定价计算器
def pricing_calculator_page():
    st.title("物流定价计算器")
    conn, c = get_db()
    uid = current_user_id()

    products = pd.read_sql(
        "SELECT id, name FROM products WHERE user_id = ?", conn, params=(uid,)
    )
    if products.empty:
        st.warning("请先添加产品")
        return

    product_id = st.selectbox(
        "选择产品",
        products['id'],
        format_func=lambda x: (
            f"{x} - "
            f"{products.loc[products['id'] == x, 'name'].values[0]}"
        ),
        key="pricing_product_selectbox"
    )

    product = c.execute(
        "SELECT * FROM products "
        "WHERE id = ? AND user_id = ?",
        (product_id, uid)
    ).fetchone()
    if not product:
        st.error("产品不存在")
        return
    product_dict = dict(product)

    # 读取用户物流
    land_logistics = pd.read_sql(
        "SELECT * FROM logistics "
        "WHERE type='land' AND user_id = ?",
        conn, params=(uid,)
    ).to_dict(orient='records')
    air_logistics = pd.read_sql(
        "SELECT * FROM logistics "
        "WHERE type='air' AND user_id = ?",
        conn, params=(uid,)
    ).to_dict(orient='records')

    if not land_logistics or not air_logistics:
        st.warning("请先配置物流规则")
        return

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

    # 自动选择最优物流
    st.subheader("物流自动选择")
    land_avg = np.mean(
        [(log['min_days'] + log['max_days']) / 2 for log in land_logistics]
    )
    air_avg = np.mean(
        [(log['min_days'] + log['max_days']) / 2 for log in air_logistics]
    )

    fast_land = [
        log for log in land_logistics
        if (log['min_days'] + log['max_days']) / 2 < land_avg
    ]
    fast_air = [
        log for log in air_logistics
        if (log['min_days'] + log['max_days']) / 2 < air_avg
    ]

    if not fast_land or not fast_air:
        st.warning("没有符合条件的物流方式")
        return

    land_df = pd.DataFrame(fast_land)
    air_df = pd.DataFrame(fast_air)

    land_df['cost'] = land_df.apply(
        lambda row: calculate_logistic_cost(row, product_dict), axis=1
    )
    air_df['cost'] = air_df.apply(
        lambda row: calculate_logistic_cost(row, product_dict), axis=1
    )

    land_df = land_df.dropna(subset=['cost'])
    air_df = air_df.dropna(subset=['cost'])

    if land_df.empty or air_df.empty:
        st.warning("没有有效的物流计算结果")
        return

    best_land = land_df.loc[land_df['cost'].idxmin()]
    best_air = air_df.loc[air_df['cost'].idxmin()]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("推荐陆运")
        st.metric("物流方式", best_land['name'])
        st.metric("时效", f"{best_land['min_days']}-{best_land['max_days']}天")
        st.metric("运费(元)", f"{best_land['cost']:.2f}")

    with col2:
        st.subheader("推荐空运")
        st.metric("物流方式", best_air['name'])
        st.metric("时效", f"{best_air['min_days']}-{best_air['max_days']}天")
        st.metric("运费(元)", f"{best_air['cost']:.2f}")

    # 最终定价
    land_price, air_price, land_cost, air_cost = calculate_pricing(
        product_dict, best_land, best_air
    )

    if land_price and air_price:
        st.subheader("最终定价")
        col1, col2 = st.columns(2)
        col1.metric(
            "陆运价格(元)", f"{land_price:.2f}",
            delta=f"运费: ¥{land_cost:.2f}"
        )
        col2.metric(
            "空运价格(元)", f"{air_price:.2f}",
            delta=f"运费: ¥{air_cost:.2f}"
        )

        # 明细
        with st.expander("定价明细分析"):
            cost_data = pd.DataFrame({
                "项目": ["产品单价", "发货方运费", "代贴单费用", "陆运运费", "空运运费"],
                "金额(元)": [
                    product_dict['unit_price'],
                    product_dict['shipping_fee'],
                    product_dict['labeling_fee'],
                    land_cost,
                    air_cost
                ]
            })
            st.dataframe(cost_data)

            fee_data = pd.DataFrame({
                "费用类型": ["画线折扣", "活动折扣", "推广费用", "佣金", "提现费", "支付手续费"],
                "费率": [
                    f"{product_dict['discount_rate']*100:.1f}%",
                    f"{product_dict['promotion_discount']*100:.1f}%",
                    f"{product_dict['promotion_cost_rate']*100:.1f}%",
                    f"{product_dict['commission_rate']*100:.1f}%",
                    f"{product_dict['withdrawal_fee_rate']*100:.1f}%",
                    f"{product_dict['payment_processing_fee']*100:.1f}%"
                ]
            })
            st.dataframe(fee_data)

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

            profit_data = pd.DataFrame({
                "物流类型": ["陆运", "空运"],
                "总成本(元)": [land_total_cost, air_total_cost],
                "销售价格(元)": [land_price, air_price],
                "利润(元)": [land_profit, air_profit],
                "利润率": [
                    f"{land_margin*100:.2f}%",
                    f"{air_margin*100:.2f}%"
                ]
            })
            st.dataframe(profit_data)

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


# -------------------------- 页面：用户管理
def user_management_page():
    st.title("用户管理")
    conn, c = get_db()

    with st.expander("添加新用户"):
        with st.form("add_user_form"):
            username = st.text_input("用户名*")
            password = st.text_input("密码*", type="password")
            role = st.selectbox("角色*", ["admin", "user"])
            if st.form_submit_button("添加用户"):
                if not username or not password:
                    st.error("请填写所有必填字段")
                else:
                    if create_user(username, password, role):
                        st.success("用户添加成功！")
                        st.rerun()
                    else:
                        st.error("用户名已存在")

    st.subheader("用户列表")
    users = pd.read_sql("SELECT id, username, role FROM users", conn)
    if users.empty:
        st.info("暂无用户数据")
        return

    choice = st.radio(
        "请选择一名用户",
        options=users.itertuples(index=False),
        format_func=lambda x: f"{x.id} - {x.username} ({x.role})"
    )
    if choice:
        user_id = choice.id
        st.write("---")
        st.write(f"**已选用户：** {choice.username}（{choice.role}）")

        with st.expander("重置密码"):
            with st.form("reset_password_form"):
                new_pwd = st.text_input("新密码*", type="password")
                if st.form_submit_button("确认重置"):
                    if not new_pwd:
                        st.error("请输入新密码")
                    else:
                        hashed = hashlib.sha256(new_pwd.encode()).hexdigest()
                        c.execute(
                            "UPDATE users SET password=? WHERE id=?",
                            (hashed, user_id)
                        )
                        conn.commit()
                        st.success("密码已更新！")
                        st.rerun()

        if st.button("删除用户", key=f"del_user_{user_id}"):
            if user_id == st.session_state.user['id']:
                st.error("不能删除当前登录用户")
            else:
                c.execute("DELETE FROM users WHERE id=?", (user_id,))
                conn.commit()
                st.success("用户已删除！")
                st.rerun()


# -------------------------------------------------
# 登录/注册页面（已用 st.form 避免焦点丢失）
# -------------------------------------------------
def login_or_register_page():
    st.title("物流定价系统 - 登录 / 注册")
    tab_login, tab_register = st.tabs(["登录", "注册"])

    # 登录
    with tab_login:
        with st.form("login_form"):
            identifier = st.text_input("用户名或邮箱")
            pwd = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")
            if submitted:
                user = verify_user(identifier, pwd)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("用户名/邮箱或密码错误")

    # 注册
    with tab_register:
        with st.form("register_form"):
            username = st.text_input("用户名")
            email = st.text_input("邮箱")
            pwd1 = st.text_input("密码", type="password")
            pwd2 = st.text_input("确认密码", type="password")
            submitted = st.form_submit_button("注册")
            if submitted:
                if pwd1 != pwd2:
                    st.error("两次密码不一致")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    st.error("邮箱格式不正确")
                elif create_user(username, pwd1, role='user', email=email):
                    st.success("注册成功，请登录")
                else:
                    st.error("用户名或邮箱已注册")


# -------------------------- 主入口
def main():
    st.set_page_config(page_title="物流定价系统", page_icon="📦", layout="wide")
    st.sidebar.subheader("调试信息")
    st.session_state.debug_mode = st.sidebar.checkbox("启用调试模式", False)

    init_db()

    if 'user' not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        login_or_register_page()
        return

    # 主界面
    st.sidebar.title(f"欢迎, {st.session_state.user['username']}")
    st.sidebar.subheader(f"角色: {st.session_state.user['role']}")

    menu_options = ["产品管理", "物流规则", "定价计算器"]
    if st.session_state.user['role'] == 'admin':
        menu_options.append("用户管理")

    selected_page = st.sidebar.selectbox("导航", menu_options)

    if selected_page == "产品管理":
        products_page()
    elif selected_page == "物流规则":
        logistics_page()
    elif selected_page == "定价计算器":
        pricing_calculator_page()
    elif selected_page == "用户管理":
        user_management_page()

    if st.sidebar.button("退出登录", key="logout"):
        st.session_state.user = None
        st.session_state.pop('products_data', None)
        st.session_state.pop('logistics_data', None)
        st.rerun()


if __name__ == "__main__":
    main()
