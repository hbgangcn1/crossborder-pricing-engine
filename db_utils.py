import os
import sqlite3
import streamlit as st
import hashlib


def get_db():
    """获取数据库连接和游标"""
    db_path = os.path.join(os.path.dirname(__file__), "pricing_system.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


def current_user_id():
    """获取当前用户ID"""
    return st.session_state.user["id"]

# 数据库升级相关函数


def _upgrade_logistics_battery():
    """升级物流表电池相关字段"""
    conn, c = get_db()
    c.execute("PRAGMA table_info(logistics)")
    cols = [col[1] for col in c.fetchall()]
    if "battery_capacity_limit_wh" not in cols:
        c.execute(
            "ALTER TABLE logistics ADD COLUMN "
            "battery_capacity_limit_wh REAL"
        )
    if "require_msds" not in cols:
        c.execute(
            "ALTER TABLE logistics ADD COLUMN "
            "require_msds INTEGER DEFAULT 0"
        )
    conn.commit()


def _upgrade_logistics_volume_coefficient():
    """升级物流表体积系数字段"""
    conn, c = get_db()
    c.execute("PRAGMA table_info(logistics)")
    cols = [col[1] for col in c.fetchall()]
    if "volume_coefficient" not in cols:
        c.execute(
            "ALTER TABLE logistics ADD COLUMN "
            "volume_coefficient REAL DEFAULT 5000"
        )
    conn.commit()


def _upgrade_max_size_to_sides(table: str):
    """升级旧表结构：max_size -> max_sum_of_sides + max_longest_side"""
    conn, c = get_db()
    # 1. 检查是否已有新字段
    c.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in c.fetchall()]
    if "max_sum_of_sides" in cols and "max_longest_side" in cols:
        return  # 已升级过
    # 2. 重命名旧表
    c.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
    # 3. 创建包含所有字段的新表
    c.execute(
        """
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
            volume_coefficient REAL DEFAULT 5000,
            allow_battery INTEGER,
            allow_flammable INTEGER
        )
        """
    )
    # 4. 迁移旧数据
    c.execute(
        """
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
        """
    )
    # 5. 清理旧表
    c.execute(f"DROP TABLE {table}_old")
    conn.commit()


def _upgrade_table_user_id(table: str):
    """给旧表加 user_id 字段（如存在）"""
    conn, c = get_db()
    cols = [col[1]
            for col in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if "user_id" in cols:
        return
    c.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
    if table == "logistics":
        c.execute(
            """
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
                min_weight INTEGER,
                max_weight INTEGER,
                max_sum_of_sides INTEGER,
                max_longest_side INTEGER,
                volume_mode TEXT DEFAULT 'none',
                longest_side_threshold INTEGER DEFAULT 0,
                volume_coefficient REAL DEFAULT 5000,
                allow_battery INTEGER,
                allow_flammable INTEGER
            )
            """
        )
        c.execute(
            """
            INSERT INTO logistics (
                user_id, name, type, min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight,
                max_sum_of_sides, max_longest_side,
                volume_mode, longest_side_threshold,
                allow_battery, allow_flammable
            )
            SELECT
                (SELECT id FROM users WHERE role='admin' LIMIT 1),
                name, type, min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight,
                COALESCE(max_size, 0), COALESCE(max_size, 0),
                volume_mode, longest_side_threshold,
                allow_battery, allow_flammable
            FROM logistics_old
            """
        )
    elif table == "products":
        c.execute(
            """
            CREATE TABLE products (
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
                labeling_fee REAL
            )
            """
        )
        c.execute(
            """
            INSERT INTO products (
                user_id, name, russian_name, category, model,
                unit_price, weight_g, length_cm, width_cm, height_cm,
                is_cylinder, cylinder_diameter,
                has_battery, battery_capacity_wh, battery_capacity_mah,
                battery_voltage, has_msds, has_flammable,
                shipping_fee, labeling_fee
            )
            SELECT
                (SELECT id FROM users WHERE role='admin' LIMIT 1),
                name, russian_name, category, model,
                unit_price, weight_g, length_cm, width_cm, height_cm,
                is_cylinder, cylinder_diameter,
                has_battery, battery_capacity_wh, battery_capacity_mah,
                battery_voltage, has_msds, has_flammable,
                shipping_fee, labeling_fee
            FROM products_old
            """
        )
    c.execute(f"DROP TABLE {table}_old")
    conn.commit()


def _upgrade_old_volume_battery():
    """升级旧表体积和电池因子字段"""
    _upgrade_logistics_volume_coefficient()
    conn, c = get_db()
    cols = [col[1]
            for col in c.execute("PRAGMA table_info(logistics)").fetchall()]
    # 如果旧表里还有 volume_factor / battery_factor 就 DROP COLUMN
    # SQLite ≥ 3.35 支持 DROP COLUMN；低版本需重建表
    for col in ["volume_factor", "battery_factor"]:
        if col in cols:
            c.execute(f"ALTER TABLE logistics DROP COLUMN {col}")
    conn.commit()


def _upgrade_logistics_new_fields():
    """升级：新增重量计费字段、电池容量限制字段"""
    conn, c = get_db()
    cols = [col[1]
            for col in c.execute("PRAGMA table_info(logistics)").fetchall()]
    new_cols = {
        "battery_capacity_limit_wh": "REAL DEFAULT 0",
        "require_msds": "INTEGER DEFAULT 0",
        "fee_mode": "TEXT DEFAULT 'base_plus_continue'",
        "first_fee": "REAL DEFAULT 0",
        "first_weight_g": "INTEGER DEFAULT 0",
        "continue_fee": "REAL DEFAULT 0",
        "continue_unit": "TEXT DEFAULT '100'",
        "volume_coefficient": "INTEGER DEFAULT 5000",
        "price_min_rub": "REAL DEFAULT 0",
        "max_second_side": "INTEGER DEFAULT 0",
        "min_length": "INTEGER DEFAULT 0",
        "max_cylinder_sum": "INTEGER DEFAULT 0",
        "max_cylinder_length": "INTEGER DEFAULT 0",
        "min_cylinder_length": "INTEGER DEFAULT 0",
    }
    for col, def_sql in new_cols.items():
        if col not in cols:
            c.execute(f"ALTER TABLE logistics ADD COLUMN {col} {def_sql}")
    conn.commit()


def create_user(username, password, role="user", email=None):
    """创建用户"""
    conn, c = get_db()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute(
            "INSERT INTO users (username, password, role, email) "
            "VALUES (?, ?, ?, ?)",
            (username, hashed, role, email),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(identifier, password):
    """验证用户"""
    conn, c = get_db()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    user = c.execute(
        "SELECT * FROM users "
        "WHERE (username = ? OR email = ?) AND password = ?",
        (
            identifier,
            identifier,
            hashed,
        ),
    ).fetchone()
    return dict(user) if user else None


def init_db():
    """初始化数据库"""
    conn, c = get_db()
    # 1. 三张基础表：users / products / logistics
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            email TEXT UNIQUE
        )
        """
    )
    c.execute(
        """
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
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS logistics (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT,
            type TEXT,
            min_days INTEGER,
            max_days INTEGER,
            price_limit REAL,
            price_limit_rub REAL,
            price_min_rub REAL DEFAULT 0,
            base_fee REAL DEFAULT 0,
            min_weight INTEGER,
            max_weight INTEGER,
            max_sum_of_sides INTEGER,
            max_longest_side INTEGER,
            max_second_side INTEGER DEFAULT 0,
            min_length INTEGER DEFAULT 0,
            max_cylinder_sum INTEGER DEFAULT 0,
            max_cylinder_length INTEGER DEFAULT 0,
            min_cylinder_length INTEGER DEFAULT 0,
            volume_mode TEXT
                CHECK(
                    volume_mode IN (
                        'none',
                        'max_actual_vs_volume',
                        'longest_side'
                    )
                )
                DEFAULT 'none',
            longest_side_threshold INTEGER DEFAULT 0,
            allow_battery INTEGER,
            allow_flammable INTEGER,
            battery_capacity_limit_wh REAL DEFAULT 0,
            require_msds INTEGER DEFAULT 0,
            fee_mode TEXT DEFAULT 'base_plus_continue',
            first_fee REAL DEFAULT 0,
            first_weight_g INTEGER DEFAULT 0,
            continue_fee REAL DEFAULT 0,
            continue_unit TEXT DEFAULT '100',
            volume_coefficient REAL DEFAULT 5000
        )
        """
    )
    conn.commit()
    # 2. 升级旧表（只跑一次）
    _upgrade_table_user_id("products")
    _upgrade_table_user_id("logistics")
    _upgrade_max_size_to_sides("logistics")
    _upgrade_old_volume_battery()
    _upgrade_logistics_new_fields()
    # 3. 初始管理员
    if not verify_user("admin", "admin123"):
        create_user("admin", "admin123", "admin")
