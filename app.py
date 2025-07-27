import datetime
import hashlib
import math
import pandas as pd
import re
import sqlite3
import streamlit as st
import threading
import time
import os
from exchange_service import ExchangeRateService

# -------------------------- 线程局部存储
thread_local = threading.local()


# -------------------------- 莫斯科交易所拉取离岸人民币-卢布实时成交价
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moex_rate.json")

# -------------------------- 数据库连接（绝对路径）
@st.cache_resource
def get_db():
    db_path = os.path.join(os.path.dirname(__file__), "pricing_system.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


# ----------------------------------------------------------
# 升级旧表结构：max_size -> max_sum_of_sides + max_longest_side
# ----------------------------------------------------------
def _upgrade_max_size_to_sides(table: str):
    conn, c = get_db()

    # 1. 检查是否已有新字段
    c.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in c.fetchall()]
    if "max_sum_of_sides" in cols and "max_longest_side" in cols:
        return  # 已升级过

    # 2. 重命名旧表
    c.execute(f"ALTER TABLE {table} RENAME TO {table}_old")

    # 3. 创建包含所有字段的新表
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
            max_sum_of_sides INTEGER,
            max_longest_side INTEGER,
            volume_mode TEXT
                CHECK(volume_mode IN ('none',
                                      'max_actual_vs_volume',
                                      'longest_side'))
                DEFAULT 'none',
            longest_side_threshold INTEGER DEFAULT 0,
            allow_battery INTEGER,
            allow_flammable INTEGER
        )
    """)

    # 4. 迁移旧数据
    c.execute("""
        INSERT INTO logistics (
            user_id, name, type, min_days, max_days, price_limit,
            base_fee, weight_factor, volume_factor, battery_factor,
            min_weight, max_weight,
            max_sum_of_sides, max_longest_side,
            volume_mode, longest_side_threshold,
            allow_battery, allow_flammable
        )
        SELECT
            user_id, name, type, min_days, max_days, price_limit,
            base_fee, weight_factor, volume_factor, battery_factor,
            min_weight, max_weight,
            COALESCE(max_size, 0), COALESCE(max_size, 0),
            volume_mode, longest_side_threshold,
            allow_battery, allow_flammable
        FROM logistics_old
    """)

    # 5. 清理旧表
    c.execute(f"DROP TABLE {table}_old")
    conn.commit()


# ----------------------------------------------------------
# 升级旧表结构：增加 user_id 及体积重量新字段
# ----------------------------------------------------------
def _upgrade_table_user_id(table: str):
    conn, c = get_db()

    # 先查当前列
    c.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in c.fetchall()]

    # 如果已经带 user_id，则无需再升级
    if "user_id" in cols:
        return  # 已升级过，直接退出

    # 1. 重命名旧表
    c.execute(f"ALTER TABLE {table} RENAME TO {table}_old")

    # 2. 按新结构创建表（logistics 已不含 max_volume_weight）
    if table == "logistics":
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
                volume_mode TEXT
                    CHECK(volume_mode IN ('none',
                                          'max_actual_vs_volume',
                                          'longest_side'))
                    DEFAULT 'none',
                longest_side_threshold INTEGER DEFAULT 0,
                allow_battery INTEGER,
                allow_flammable INTEGER
            )
        """)
        # 迁移旧数据：把旧字段映射到新字段
        c.execute("""
            INSERT INTO logistics (
                user_id, name, type, min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight, max_size,
                volume_mode, longest_side_threshold,
                allow_battery, allow_flammable
            )
            SELECT
                (SELECT id FROM users WHERE role='admin' LIMIT 1),
                name, type, min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight, max_size,
                'none', 0,  -- 旧数据统一设为不计算体积重量
                allow_battery, allow_flammable
            FROM logistics_old
        """)
    elif table == "products":
        # products 表结构不变，仅加 user_id
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
                payment_processing_fee REAL DEFAULT 0.01
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

    # 3. 删除旧表
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
            unit_price REAL,
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
            shipping_fee REAL,
            labeling_fee REAL,
            promotion_discount     REAL DEFAULT 0.05,
            promotion_cost_rate    REAL DEFAULT 0.115,
            target_profit_margin   REAL DEFAULT 0.5,
            commission_rate        REAL DEFAULT 0.17,
            withdrawal_fee_rate    REAL DEFAULT 0.01,
            payment_processing_fee REAL DEFAULT 0.01
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
            volume_mode TEXT
                    CHECK(volume_mode IN ('none',
                                        'max_actual_vs_volume',
                                        'longest_side'))
                    DEFAULT 'none',
            longest_side_threshold INTEGER DEFAULT 0,
            allow_battery INTEGER,
            allow_flammable INTEGER
        )
    """)
    conn.commit()

    # 2. 升级旧数据（如存在）
    _upgrade_table_user_id("products")
    _upgrade_table_user_id("logistics")
    _upgrade_max_size_to_sides("logistics")

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
        # 1. 重量限制
        w = product.get('weight_g', 0)
        min_w = logistic.get('min_weight', 0)
        max_w = logistic.get('max_weight', 10**9)
        if w < min_w or w > max_w:
            return None

        # 2. 三边之和限制 + 最长边限制
        max_sum     = logistic.get('max_sum_of_sides', 10**9)
        max_longest = logistic.get('max_longest_side', 10**9)
        sides = [
            product.get('length_cm', 0),
            product.get('width_cm',  0),
            product.get('height_cm', 0)
        ]
        if sum(sides) > max_sum:
            return None
        if any(s > max_longest for s in sides):
            return None

        # 3. 电池、易燃
        if product.get('has_battery') and not logistic.get('allow_battery'):
            return None
        if product.get('has_flammable') and not logistic.get('allow_flammable'):
            return None

        # 4. 体积重量计费逻辑
        volume_mode = logistic.get('volume_mode', 'none')
        longest_side = max(product.get('length_cm', 0),
                           product.get('width_cm', 0),
                           product.get('height_cm', 0))
        volume_weight = (product['length_cm'] *
                         product['width_cm'] *
                         product['height_cm']) / 6000   # 6000 可改

        # 4-1 不计算
        if volume_mode == 'none':
            billing_weight = w / 1000   # kg
        # 4-2 取大者
        elif volume_mode == 'max_actual_vs_volume':
            billing_weight = max(w / 1000, volume_weight)
        # 4-3 最长边触发
        elif volume_mode == 'longest_side':
            threshold = logistic.get('longest_side_threshold', 0)
            if longest_side > threshold:
                billing_weight = max(w / 1000, volume_weight)
            else:
                billing_weight = w / 1000
        else:
            billing_weight = w / 1000

        # 5. 费用计算
        cost = logistic.get('base_fee', 0)
        if logistic.get('weight_factor'):
            cost += logistic['weight_factor'] * math.ceil(billing_weight * 1000)
        if logistic.get('volume_factor') and volume_mode != 'none':
            cost += logistic['volume_factor'] * math.ceil(volume_weight * 10)
        if product.get('has_battery') and logistic.get('battery_factor'):
            cost += logistic['battery_factor']
        return cost
    except Exception as e:
        st.error(f"物流费用计算错误: {e}")
        return None


# -------------------------- 定价
def calculate_pricing(product, land_logistics, air_logistics):
    import time
    from functools import lru_cache

    start_total = time.time()

    # ---------- 1. 基础数据 ----------
    t0 = time.time()
    unit_price   = float(product['unit_price'])
    labeling_fee = float(product['labeling_fee'])
    shipping_fee = float(product['shipping_fee'])
    rate         = ExchangeRateService().get_exchange_rate()
    print(f"[TIME] 基础数据读取: {(time.time() - t0) * 1000:.2f} ms")

    # ---------- 2. 缓存版 calculate_logistic_cost ----------
    @lru_cache(maxsize=256)
    def cached_cost(log_tuple, prod_tuple):
        return calculate_logistic_cost(dict(log_tuple), dict(prod_tuple))

    # ---------- 3. 过滤可用物流 ----------
    t0 = time.time()

    def _cost_and_filter(logistics):
        res = []
        for log in logistics:
            cost = cached_cost(tuple(log.items()), tuple(product.items()))
            if cost is None:
                continue
            limit = log.get('price_limit') or 0
            # 粗略估算价格
            rough = (
                (unit_price + labeling_fee + shipping_fee + 15 * rate + cost)
                * (1 + product['target_profit_margin'])
                / (
                    (1 - product['promotion_discount'])
                    * (1 - product['commission_rate'])
                    * (1 - product['withdrawal_fee_rate'])
                    * (1 - product['payment_processing_fee'])
                )
            )
            if limit == 0 or rough <= limit:
                res.append((log, cost))
        return res

    land_candidates = _cost_and_filter(land_logistics)
    air_candidates  = _cost_and_filter(air_logistics)
    print(f"[TIME] 物流过滤: {(time.time() - t0) * 1000:.2f} ms")

    # ---------- 4. 取最优 ----------
    t0 = time.time()
    land_best = min(land_candidates, key=lambda x: x[1]) if land_candidates else (None, None)
    air_best  = min(air_candidates,  key=lambda x: x[1]) if air_candidates  else (None, None)

    # ---------- 5. 最终价格 ----------
    def _final_price(cost):
        total_cost = (
            unit_price +
            labeling_fee +
            shipping_fee +
            cost +
            15 * rate
        )
        denominator = (
            (1 - product['promotion_discount'])
            * (1 - product['commission_rate'])
            * (1 - product['withdrawal_fee_rate'])
            * (1 - product['payment_processing_fee'])
        )
        return round(total_cost * (1 + product['target_profit_margin']) / denominator, 2)

    land_price = _final_price(land_best[1]) if land_best[0] else None
    air_price  = _final_price(air_best[1])  if air_best[0]  else None
    print(f"[TIME] 价格计算: {(time.time() - t0) * 1000:.2f} ms")

    print(f"[TIME] 总耗时: {(time.time() - start_total) * 1000:.2f} ms")
    return (
        land_price, air_price,
        land_best[1] if land_best[0] else None,
        air_best[1]  if air_best[0]  else None,
        land_best[0]['name'] if land_best[0] else None,
        air_best[0]['name']  if air_best[0]  else None
    )


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

        st.subheader("基本信息")
        name = st.text_input("产品名称*")
        russian_name = st.text_input("俄文名称")
        category = st.text_input("产品类别")
        model = st.text_input("型号")
        unit_price = st.number_input("进货单价（元）*", min_value=0.0, value=0.0, step=0.01)

        st.subheader("物理规格")
        # 重量独占一行
        weight_g = st.number_input("重量(g)*", min_value=0, value=0)

        col1, col2, col3 = st.columns(3)
        length_cm = col1.number_input("长(cm)*", min_value=0, value=0)
        width_cm = col2.number_input("宽(cm)*", min_value=0, value=0)
        height_cm = col3.number_input("高(cm)*", min_value=0, value=0)

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
        shipping_fee = col1.number_input("发货方运费(元)*", min_value=0.0, value=0.0)
        labeling_fee = st.number_input("代贴单费用(元)*", min_value=0.0, value=0.0)

        st.subheader("定价参数")
        col1, col2 = st.columns(2)
        _promotion_discount = col2.slider("活动折扣率", 0.0, 1.0, 0.05, 0.01)
        _promotion_cost_rate = col1.slider("推广费用率", 0.0, 1.0, 0.115, 0.01)
        _target_profit_margin = col1.slider("目标利润率", 0.0, 1.0, 0.5, 0.01)
        _commission_rate = col2.slider("佣金率", 0.0, 1.0, 0.175, 0.01)
        _withdrawal_fee_rate = col1.slider("提现费率", 0.0, 0.1, 0.01, 0.001)
        _payment_processing_fee = col2.slider("支付手续费率", 0.0, 0.1, 0.013, 0.001)

        if st.button("添加产品"):
            required = [name, weight_g, length_cm, width_cm, height_cm, unit_price]
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
                    "is_cylinder, cylinder_diameter, "
                    "has_battery, battery_capacity_wh, battery_capacity_mah, battery_voltage, "
                    "has_msds, has_flammable, "
                    "unit_price, shipping_fee, labeling_fee) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uid, name, russian_name, category, model,
                        weight_g, length_cm, width_cm, height_cm,
                        int(is_cylinder), cylinder_diameter,
                        int(has_battery), battery_capacity_wh,
                        battery_capacity_mah, battery_voltage,
                        int(has_msds), int(has_flammable),
                        unit_price, shipping_fee, labeling_fee
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
        st.subheader("基本信息")
        name = st.text_input("产品名称*")
        russian_name = st.text_input("俄文名称")
        category = st.text_input("产品类别")
        model = st.text_input("型号")
        unit_price = st.number_input("进货单价（元）*", min_value=0.0, value=0.0, step=0.01)
        st.subheader("物理规格")
        # 重量独占一行
        weight_g = st.number_input("重量(g)*", min_value=0, value=0)

        col1, col2, col3 = st.columns(3)
        length_cm = col1.number_input("长(cm)*", min_value=0, value=0)
        width_cm = col2.number_input("宽(cm)*", min_value=0, value=0)
        height_cm = col3.number_input("高(cm)*", min_value=0, value=0)

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
        shipping_fee = col2.number_input(
            "发货方运费(元)*",
            value=vals['shipping_fee']
        )
        labeling_fee = st.number_input("代贴单费用(元)*", value=vals['labeling_fee'])

        st.subheader("定价参数")
        col1, col2 = st.columns(2)
        promotion_discount = col2.slider(
            "活动折扣率", 0.0, 1.0, vals['promotion_discount'], 0.01
        )
        promotion_cost_rate = col1.slider(
            "推广费用率", 0.0, 1.0, vals['promotion_cost_rate'], 0.01
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
                 shipping_fee, labeling_fee, promotion_discount,
                 promotion_cost_rate, target_profit_margin, commission_rate,
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


# -------------------------- 页面：物流规则（已更新）
def logistics_page():
    conn, c = get_db()
    uid = current_user_id()

    if st.session_state.get("edit_logistic_id"):
        edit_logistic_form()
        return

    # ------------------------------------------------------------------
    # 添加物流规则
    # ------------------------------------------------------------------
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
            price_limit_rub = st.number_input(
                "限价(卢布)",
                min_value=0.0,
                value=0.0,
                help="系统会按实时 CNH/RUB 汇率折算成人民币参与定价"
            )
            st.subheader("费用结构")
            base_fee = st.number_input("基础费用(元)", value=0.0)
            weight_factor = st.number_input(
                "每克费用(元)",
                min_value=0.0,
                value=0.0,
                step=0.00001,
                format="%.5f",
                help="例如 0.05 元/g"
            )
            volume_factor = st.number_input("每10kg体积费用(元)", value=0.0)
            battery_factor = st.number_input("电池附加费(元)", value=0.0)

            st.subheader("限制条件")
            min_weight = st.number_input("最小重量(g)", value=0)
            max_weight = st.number_input("最大重量(g)", value=0)
            max_sum_of_sides = st.number_input("三边之和限制(cm)", value=0)
            max_longest_side = st.number_input("最长边限制(cm)",   value=0)

            # 新增：体积重量计费方式
            volume_mode = st.selectbox(
                "体积重量计费方式",
                ["none", "max_actual_vs_volume", "longest_side"],
                format_func=lambda x: {
                    "none": "不计算体积重量",
                    "max_actual_vs_volume": "取实际重量与体积重量较大者",
                    "longest_side": "最长边超过阈值时按体积重量计费"
                }[x]
            )
            longest_side_threshold = 0
            if volume_mode == "longest_side":
                longest_side_threshold = st.number_input(
                    "最长边阈值(cm)",
                    min_value=0,
                    value=0
                )

            st.subheader("特殊物品限制")
            allow_battery = st.checkbox("允许运输含电池产品")
            allow_flammable = st.checkbox("允许运输易燃液体")

            if st.form_submit_button("添加物流规则"):
                if not name or not min_days or not max_days:
                    st.error("请填写所有必填字段")
                else:
                    # 实时折算：卢布 → 人民币
                    rate = ExchangeRateService().get_exchange_rate()
                    price_limit_cny = round(price_limit_rub / rate, 4)

                    type_en = {"陆运": "land", "空运": "air"}[logistic_type]
                    c.execute(
                        "INSERT INTO logistics ("
                        "user_id, name, type, min_days, max_days, price_limit, price_limit_rub, base_fee, "
                        "weight_factor, volume_factor, battery_factor, min_weight, "
                        "max_weight, max_sum_of_sides, max_longest_side, volume_mode, longest_side_threshold, "
                        "allow_battery, allow_flammable) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            uid, name, type_en, min_days, max_days, price_limit_cny, price_limit_rub,
                            base_fee, weight_factor, volume_factor, battery_factor,
                            min_weight, max_weight,
                            max_sum_of_sides, max_longest_side,
                            volume_mode, longest_side_threshold,
                            int(allow_battery), int(allow_flammable)
                        )
                    )
                    conn.commit()
                    st.success("物流规则添加成功！")
                    st.rerun()

    # ------------------------------------------------------------------
    # 物流列表
    # ------------------------------------------------------------------
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
                    f"{row['min_days']}-{row['max_days']}天 | "
                    f"三边和≤{row['max_sum_of_sides']}cm | "
                    f"最长边≤{row['max_longest_side']}cm"
                )
                col_edit, col_del = st.columns(2)
                with col_edit:
                    if st.button("编辑", key=f"edit_land_{row['id']}"):
                        st.session_state.edit_logistic_id = row['id']
                        st.rerun()
                with col_del:
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
                    f"{row['min_days']}-{row['max_days']}天 | "
                    f"三边和≤{row['max_sum_of_sides']}cm | "
                    f"最长边≤{row['max_longest_side']}cm"
                )
                col_edit, col_del = st.columns(2)
                with col_edit:
                    if st.button("编辑", key=f"edit_air_{row['id']}"):
                        st.session_state.edit_logistic_id = row['id']
                        st.rerun()
                with col_del:
                    if st.button("删除", key=f"del_air_{row['id']}"):
                        c.execute(
                            "DELETE FROM logistics WHERE id=? AND user_id=?",
                            (row['id'], uid)
                        )
                        conn.commit()
                        st.rerun()
        else:
            st.info("暂无空运数据")


# -------------------------- 物流编辑表单（已更新）
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
        typ = st.selectbox(
            "物流类型",
            ["陆运", "空运"],
            index=0 if vals['type'] == 'land' else 1
        )
        min_days = st.number_input("最快时效(天)", value=vals['min_days'])
        max_days = st.number_input("最慢时效(天)", value=vals['max_days'])
        price_limit_rub = st.number_input(
            "限价(卢布)",
            min_value=0.0,
            value=vals.get('price_limit_rub', 0.0)
        )
        base_fee = st.number_input("基础费用", value=vals['base_fee'])
        weight_factor = st.number_input(
            "每克费用",
            value=vals['weight_factor'],
            step=0.00001,
            format="%.5f"
        )
        volume_factor = st.number_input(
            "每10kg体积费用",
            value=vals['volume_factor']
        )
        battery_factor = st.number_input("电池附加费", value=vals['battery_factor'])

        min_weight = st.number_input("最小重量(g)", value=vals['min_weight'])
        max_weight = st.number_input("最大重量(g)", value=vals['max_weight'])
        max_sum_of_sides = st.number_input(
            "三边之和限制(cm)",
            value=vals.get('max_sum_of_sides', 0)
        )
        max_longest_side = st.number_input(
            "最长边限制(cm)",
            value=vals.get('max_longest_side', 0)
        )

        # ---- 新增：体积重量计费方式 ----
        volume_mode = st.selectbox(
            "体积重量计费方式",
            ["none", "max_actual_vs_volume", "longest_side"],
            index=["none", "max_actual_vs_volume", "longest_side"].index(
                vals.get('volume_mode', 'none')
            ),
            format_func=lambda x: {
                "none": "不计算体积重量",
                "max_actual_vs_volume": "取实际重量与体积重量较大者",
                "longest_side": "最长边超过阈值时按体积重量计费"
            }[x]
        )
        longest_side_threshold = 0
        if volume_mode == "longest_side":
            longest_side_threshold = st.number_input(
                "最长边阈值(cm)",
                min_value=0,
                value=vals.get('longest_side_threshold', 0)
            )

        allow_battery = st.checkbox(
            "允许电池",
            value=bool(vals['allow_battery'])
        )
        allow_flammable = st.checkbox(
            "允许易燃液体",
            value=bool(vals['allow_flammable'])
        )

        if st.form_submit_button("保存修改"):
            rate = ExchangeRateService().get_exchange_rate()
            price_limit_cny = round(price_limit_rub / rate, 4)

            c.execute(
                "UPDATE logistics SET "
                "name=?, type=?, min_days=?, max_days=?, price_limit=?, price_limit_rub=?, "
                "base_fee=?, weight_factor=?, volume_factor=?, battery_factor=?, "
                "min_weight=?, max_weight=?, max_sum_of_sides=?, max_longest_side=?, "
                "volume_mode=?, longest_side_threshold=?, allow_battery=?, allow_flammable=? "
                "WHERE id=? AND user_id=?",
                (
                    name, {"陆运": "land", "空运": "air"}[typ],
                    min_days, max_days, price_limit_cny, price_limit_rub,
                    base_fee, weight_factor, volume_factor, battery_factor,
                    min_weight, max_weight,
                    max_sum_of_sides, max_longest_side,
                    volume_mode, longest_side_threshold,
                    int(allow_battery), int(allow_flammable),
                    lid, uid
                )
            )
            conn.commit()
            st.success("修改成功！")
            del st.session_state.edit_logistic_id
            st.rerun()

    if st.button("取消"):
        del st.session_state.edit_logistic_id
        st.rerun()


# -------------------------- 页面：定价计算器（带缓存优化）
def pricing_calculator_page():
    st.session_state.t0 = time.time()
    st.write("页面开始渲染", datetime.datetime.now().strftime("%H:%M:%S"))
    st.title("物流定价计算器")

    cache_ttl = 1800  # 30 分钟

    conn, c = get_db()
    uid = current_user_id()

    # ------------- 1. 选择产品 -------------
    products = pd.read_sql(
        "SELECT id, name FROM products WHERE user_id = ?", conn, params=(uid,)
    )
    if products.empty:
        st.warning("请先添加产品")
        return

    product_id = st.selectbox(
        "选择产品",
        products['id'],
        format_func=lambda x: f"{x} - {products.loc[products['id']==x,'name'].values[0]}",
        key="pricing_product_select"
    )

    # ------------- 2. 缓存 key -------------
    cache_key = f"pricing_cache_{uid}_{product_id}"
    ts_key = f"{cache_key}_ts"

    # ------------- 3. 判断是否命中缓存 -------------
    hit_cache = (
        cache_key in st.session_state
        and ts_key in st.session_state
        and (time.time() - st.session_state[ts_key]) < cache_ttl
    )

    if hit_cache:
        # 直接读取缓存
        (
            product_dict, land_logistics, air_logistics,
            land_price, air_price, land_cost, air_cost, land_name, air_name
        ) = st.session_state[cache_key]
        st.info("✅ 已使用缓存定价结果")
    else:
        # ------------- 4. 未命中：重新查询 + 计算 -------------
        product = c.execute(
            "SELECT * FROM products WHERE id = ? AND user_id = ?",
            (product_id, uid)
        ).fetchone()
        if not product:
            st.error("产品不存在")
            return
        product_dict = dict(product)

        land_logistics = pd.read_sql(
            "SELECT * FROM logistics WHERE type='land' AND user_id = ?", conn, params=(uid,)
        ).to_dict(orient='records')
        air_logistics = pd.read_sql(
            "SELECT * FROM logistics WHERE type='air' AND user_id = ?", conn, params=(uid,)
        ).to_dict(orient='records')

        land_price, air_price, land_cost, air_cost, land_name, air_name = calculate_pricing(
            product_dict, land_logistics, air_logistics
        )

        # 写入缓存
        st.session_state[cache_key] = (
            product_dict, land_logistics, air_logistics,
            land_price, air_price, land_cost, air_cost, land_name, air_name
        )
        st.session_state[ts_key] = time.time()

    # ------------- 5. 后续逻辑保持不变 -------------
    # ---- 调试信息 ----
    st.subheader("=== DEBUG 物流淘汰原因 ===")
    for log in land_logistics + air_logistics:
        reason = _debug_filter_reason(log, product_dict)
        if reason:
            st.write(f"❌ {log['name']}（{log['type']}）被淘汰：{reason}")
        else:
            st.write(f"✅ {log['name']}（{log['type']}）可用")

    # ---- 展示结果 ----
    col1, col2 = st.columns(2)
    with col1:
        if land_price is not None:
            st.markdown(
                f"""
                <div style="font-size:24px; font-weight:bold; margin-bottom:8px;">
                    最佳陆运：<span style="color:#007acc;">{land_name}</span>
                </div>
                <div style="font-size:22px; margin-bottom:4px;">
                    物流运费：<span style="color:#d9534f;">¥{land_cost:.2f}</span>
                </div>
                <div style="font-size:22px;">
                    产品定价：<span style="color:#28a745;">¥{land_price:.2f}</span>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.info("无可用陆运")

    with col2:
        if air_price is not None:
            st.markdown(
                f"""
                <div style="font-size:24px; font-weight:bold; margin-bottom:8px;">
                    最佳空运：<span style="color:#007acc;">{air_name}</span>
                </div>
                <div style="font-size:22px; margin-bottom:4px;">
                    物流运费：<span style="color:#d9534f;">¥{air_cost:.2f}</span>
                </div>
                <div style="font-size:22px;">
                    产品定价：<span style="color:#28a745;">¥{air_price:.2f}</span>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.info("无可用空运")

    with st.expander("定价明细分析"):
        cost_data = pd.DataFrame({
            "项目": ["产品单价", "发货方运费", "代贴单费用", "陆运运费", "空运运费"],
            "金额(元)": [
                product_dict['unit_price'],
                product_dict['shipping_fee'],
                product_dict['labeling_fee'],
                land_cost if land_cost is not None else 0,
                air_cost  if air_cost  is not None else 0
            ]
        })
        st.dataframe(cost_data)

        fee_data = pd.DataFrame({
            "费用类型": ["活动折扣", "推广费用", "佣金", "提现费", "支付手续费"],
            "费率": [
                f"{product_dict['promotion_discount'] * 100:.1f}%",
                f"{product_dict['promotion_cost_rate'] * 100:.1f}%",
                f"{product_dict['commission_rate'] * 100:.1f}%",
                f"{product_dict['withdrawal_fee_rate'] * 100:.1f}%",
                f"{product_dict['payment_processing_fee'] * 100:.1f}%"
            ]
        })
        st.dataframe(fee_data)

        profit_rows = []
        for name, price, cost in (("陆运", land_price, land_cost), ("空运", air_price, air_cost)):
            if price is not None and cost is not None:
                total = (
                    product_dict['unit_price'] + cost +
                    product_dict['shipping_fee'] + product_dict['labeling_fee']
                )
                margin = (price - total) / price
                profit_rows.append({
                    "物流类型": name,
                    "总成本(元)": total,
                    "销售价格(元)": price,
                    "利润(元)": price - total,
                    "利润率": f"{margin*100:.2f}%"
                })
                if margin < product_dict.get('min_profit_margin', 0.3):
                    st.warning(
                        f"⚠️ {name}利润率低于 "
                        f"{product_dict.get('min_profit_margin',0.3)*100:.1f}%"
                    )

        if profit_rows:
            st.dataframe(pd.DataFrame(profit_rows))
        else:
            st.info("暂无可用定价结果")

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

# -------------------------- 调试：检查物流被淘汰的原因
def _debug_filter_reason(logistic, product):
    """返回淘汰原因；若可用返回 None"""

    # ---------------- 重量 ----------------
    w = product.get('weight_g', 0)
    min_w = logistic.get('min_weight', 0)
    max_w = logistic.get('max_weight', 10**9)
    if w < min_w or w > max_w:
        return f"重量 {w} g 不在 {min_w}-{max_w} g 区间"

    # ---------------- 三边之和 ----------------
    max_sum = logistic.get('max_sum_of_sides', 10**9)
    sides = [
        product.get('length_cm', 0),
        product.get('width_cm', 0),
        product.get('height_cm', 0)
    ]
    if sum(sides) > max_sum:
        return f"三边之和 {sum(sides)} cm > {max_sum} cm"

    # ---------------- 最长边 ----------------
    max_longest = logistic.get('max_longest_side', 10**9)
    for s in sides:
        if s > max_longest:
            return f"最长边 {s} cm > {max_longest} cm"

    # ---------------- 特殊物品 ----------------
    if product.get('has_battery') and not logistic.get('allow_battery'):
        return "产品含电池但物流不允许电池"
    if product.get('has_flammable') and not logistic.get('allow_flammable'):
        return "产品含易燃液体但物流不允许易燃液体"

    # ---------------- 限价 ----------------
    unit_price   = product['unit_price']
    labeling_fee = product['labeling_fee']
    shipping_fee = product['shipping_fee']
    rate         = ExchangeRateService().get_exchange_rate()
    limit        = logistic.get('price_limit') or 0

    # 用正式公式（不含画线折扣率）
    rough = (
        (unit_price + labeling_fee + shipping_fee + 15 * rate)
        * (1 + product['target_profit_margin'])
        /
        (
            (1 - product['promotion_discount'])     # 活动折扣率
            * (1 - product['commission_rate'])
            * (1 - product['withdrawal_fee_rate'])
            * (1 - product['payment_processing_fee'])
        )
    )

    if 0 < limit < rough:
        return f"估算价 ¥{rough:.2f} 超限价 ¥{limit:.2f}"

    return None

if __name__ == "__main__":
    main()
