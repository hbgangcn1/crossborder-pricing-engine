import os
import sqlite3
import streamlit as st
import hashlib
import bcrypt
from contextlib import contextmanager


def hash_password(password: str) -> str:
    """
    使用bcrypt对密码进行加盐哈希

    Args:
        password (str): 明文密码

    Returns:
        str: 加盐哈希后的密码
    """
    # 生成随机盐值
    salt = bcrypt.gensalt(rounds=12)  # 12轮加密，安全性高
    # 对密码进行哈希
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed_password: str) -> bool:
    """
    验证密码是否正确

    Args:
        password (str): 明文密码
        hashed_password (str): 存储的哈希密码

    Returns:
        bool: 密码是否正确
    """
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except (ValueError, TypeError):
        # 兼容旧的SHA256格式
        return verify_legacy_password(password, hashed_password)


def verify_legacy_password(password: str, hashed_password: str) -> bool:
    """
    验证旧的SHA256格式密码（向后兼容）

    Args:
        password (str): 明文密码
        hashed_password (str): SHA256哈希密码

    Returns:
        bool: 密码是否正确
    """
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    return legacy_hash == hashed_password


def is_bcrypt_hash(hashed_password: str) -> bool:
    """
    检查密码是否为bcrypt格式

    Args:
        hashed_password (str): 哈希密码

    Returns:
        bool: 是否为bcrypt格式
    """
    return (hashed_password.startswith('$2b$') or
            hashed_password.startswith('$2a$'))


def get_db():
    """获取数据库连接和游标"""
    db_path = os.path.join(os.path.dirname(__file__), "pricing_system.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


@contextmanager
def get_db_connection():
    """
    获取数据库连接的上下文管理器
    使用方式：
    with get_db_connection() as (conn, c):
        c.execute("SELECT * FROM users")
        # 连接会自动关闭
    """
    db_path = os.path.join(os.path.dirname(__file__), "pricing_system.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn, conn.cursor()
    finally:
        conn.close()


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
            volume_coefficient, allow_battery, allow_flammable
        )
        SELECT
            user_id, name, type, min_days, max_days, price_limit,
            base_fee, weight_factor, volume_factor, battery_factor,
            min_weight, max_weight,
            COALESCE(max_size, 0), COALESCE(max_size, 0),
            volume_mode, longest_side_threshold,
            5000, allow_battery, allow_flammable
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
                volume_coefficient, allow_battery, allow_flammable
            )
            SELECT
                (SELECT id FROM users WHERE role='admin' LIMIT 1),
                name, type, min_days, max_days, price_limit,
                base_fee, weight_factor, volume_factor, battery_factor,
                min_weight, max_weight,
                COALESCE(max_size, 0), COALESCE(max_size, 0),
                volume_mode, longest_side_threshold,
                5000, allow_battery, allow_flammable
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
                cylinder_length REAL,
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
                is_cylinder, cylinder_diameter, cylinder_length,
                has_battery, battery_capacity_wh, battery_capacity_mah,
                battery_voltage, has_msds, has_flammable,
                shipping_fee, labeling_fee
            )
            SELECT
                (SELECT id FROM users WHERE role='admin' LIMIT 1),
                name, russian_name, category, model,
                unit_price, weight_g, length_cm, width_cm, height_cm,
                is_cylinder, cylinder_diameter, 0.0,
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
            "price_limit_rub": "REAL DEFAULT 0",
            "price_min_rub": "REAL DEFAULT 0",
            "max_second_side": "INTEGER DEFAULT 0",
            "min_second_side": "INTEGER DEFAULT 0",
            "min_length": "INTEGER DEFAULT 0",
            "max_cylinder_sum": "INTEGER DEFAULT 0",
            "min_cylinder_sum": "INTEGER DEFAULT 0",
            "max_cylinder_length": "INTEGER DEFAULT 0",
            "min_cylinder_length": "INTEGER DEFAULT 0",
            "allow_battery": "INTEGER DEFAULT 0",
            "allow_flammable": "INTEGER DEFAULT 0",
            "delivery_method": "TEXT DEFAULT 'unknown'",
            "priority_group": "TEXT DEFAULT 'D'",
            "price_limit_currency": "TEXT DEFAULT 'RUB'",
            "price_min_currency": "TEXT DEFAULT 'RUB'",
        }
    for col, def_sql in new_cols.items():
        if col not in cols:
            c.execute(f"ALTER TABLE logistics ADD COLUMN {col} {def_sql}")
    conn.commit()


def _upgrade_products_cylinder_length():
    """升级：新增产品圆柱长度字段"""
    conn, c = get_db()
    cols = [col[1]
            for col in c.execute("PRAGMA table_info(products)").fetchall()]
    if "cylinder_length" not in cols:
        c.execute(
            "ALTER TABLE products ADD COLUMN cylinder_length REAL DEFAULT 0"
        )
    conn.commit()


def _upgrade_products_new_fields():
    """升级：新增产品定价相关字段"""
    conn, c = get_db()
    cols = [col[1]
            for col in c.execute("PRAGMA table_info(products)").fetchall()]
    new_cols = {
        "promotion_discount": "REAL DEFAULT 0.05",
        "promotion_cost_rate": "REAL DEFAULT 0.115",
        "target_profit_margin": "REAL DEFAULT 0.5",
        "commission_rate": "REAL DEFAULT 0.17",
        "withdrawal_fee_rate": "REAL DEFAULT 0.01",
        "payment_processing_fee": "REAL DEFAULT 0.01"
    }
    for col, def_sql in new_cols.items():
        if col not in cols:
            c.execute(f"ALTER TABLE products ADD COLUMN {col} {def_sql}")
    conn.commit()


def _upgrade_logistics_price_min():
    """升级：新增物流价格下限字段"""
    conn, c = get_db()
    cols = [col[1]
            for col in c.execute("PRAGMA table_info(logistics)").fetchall()]
    if "price_min" not in cols:
        c.execute(
            "ALTER TABLE logistics ADD COLUMN price_min REAL DEFAULT 0"
        )
    conn.commit()


def create_user(username, password, role="user", email=None):
    """创建用户"""
    # 确保数据库已初始化
    init_db()
    conn, c = get_db()

    # 检查用户名是否已存在（不区分大小写）
    existing_user = c.execute(
        "SELECT username FROM users WHERE LOWER(username) = LOWER(?)",
        (username,)
    ).fetchone()

    if existing_user:
        return False  # 用户名已存在

    # 检查邮箱是否已存在（如果提供了邮箱）
    if email:
        existing_email = c.execute(
            "SELECT email FROM users WHERE LOWER(email) = LOWER(?)",
            (email,)
        ).fetchone()

        if existing_email:
            return False  # 邮箱已存在

    # 使用bcrypt加盐哈希密码
    hashed_password = hash_password(password)

    try:
        c.execute(
            "INSERT INTO users (username, password, role, email) "
            "VALUES (?, ?, ?, ?)",
            (username, hashed_password, role, email),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(identifier, password):
    """验证用户"""
    # 确保数据库已初始化
    init_db()
    conn, c = get_db()

    # 首先根据用户名或邮箱查找用户（用户名不区分大小写）
    user = c.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?) " +
        "OR LOWER(email) = LOWER(?)",
        (identifier, identifier),
    ).fetchone()

    if user:
        stored_password = user[2]  # 存储的密码哈希

        # 使用新的密码验证函数（支持bcrypt和旧SHA256格式）
        if verify_password(password, stored_password):
            # 如果是旧格式密码，自动升级到bcrypt
            if not is_bcrypt_hash(stored_password):
                upgrade_user_password_to_bcrypt(user[0], password)

            return {
                'id': user[0],
                'username': user[1],
                'password': user[2],
                'role': user[3],
                'email': user[4]
            }

    return None


def upgrade_user_password_to_bcrypt(user_id, password):
    """
    将用户密码从SHA256格式升级到bcrypt格式

    Args:
        user_id (int): 用户ID
        password (str): 明文密码
    """
    conn, c = get_db()
    new_hashed_password = hash_password(password)

    c.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (new_hashed_password, user_id)
    )
    conn.commit()


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
            cylinder_length REAL,
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
            price_min REAL DEFAULT 0,
            price_min_rub REAL DEFAULT 0,
            base_fee REAL DEFAULT 0,
            min_weight INTEGER,
            max_weight INTEGER,
            max_sum_of_sides INTEGER,
            max_longest_side INTEGER,
            max_second_side INTEGER DEFAULT 0,
            min_second_side INTEGER DEFAULT 0,
            min_length INTEGER DEFAULT 0,
            max_cylinder_sum INTEGER DEFAULT 0,
            min_cylinder_sum INTEGER DEFAULT 0,
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
            volume_coefficient REAL DEFAULT 5000,
            delivery_method TEXT DEFAULT 'unknown',
            priority_group TEXT DEFAULT 'D',
            price_limit_currency TEXT DEFAULT 'RUB',
            price_min_currency TEXT DEFAULT 'RUB'
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
    _upgrade_products_cylinder_length()
    _upgrade_products_new_fields()
    _upgrade_logistics_price_min()
    # 3. 初始管理员（避免递归调用）
    admin_user = c.execute(
        "SELECT * FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()
    if not admin_user:
        # 使用bcrypt为默认管理员密码加盐哈希
        hashed_password = hash_password("admin123")
        c.execute(
            "INSERT INTO users (username, password, role, email) "
            "VALUES (?, ?, ?, ?)",
            ("admin", hashed_password, "admin", "admin@example.com")
        )
        conn.commit()


# 产品管理函数

def add_product(product_data):
    """添加新产品"""
    conn, c = get_db()

    # 提取产品数据
    fields = [
        'user_id', 'name', 'russian_name', 'category', 'model',
        'unit_price', 'weight_g', 'length_cm', 'width_cm', 'height_cm',
        'is_cylinder', 'cylinder_diameter', 'cylinder_length', 'has_battery',
        'battery_capacity_wh', 'battery_capacity_mah', 'battery_voltage',
        'has_msds', 'has_flammable', 'shipping_fee', 'labeling_fee',
        'promotion_discount', 'promotion_cost_rate', 'target_profit_margin',
        'commission_rate', 'withdrawal_fee_rate', 'payment_processing_fee'
    ]

    # 构建SQL语句
    placeholders = ','.join(['?' for _ in fields])
    field_names = ','.join(fields)

    # 获取值
    values = [product_data.get(field, 0) for field in fields]

    c.execute(
        f"INSERT INTO products ({field_names}) VALUES ({placeholders})",
        values
    )
    conn.commit()
    return c.lastrowid


def get_all_products_for_user(user_id):
    """获取用户的所有产品"""
    conn, c = get_db()
    products = c.execute(
        "SELECT * FROM products WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    return [dict(product) for product in products]


def get_product_by_id(product_id, user_id):
    """根据ID获取产品 - 强制要求用户ID验证"""
    if user_id is None:
        raise ValueError("user_id参数是必需的，以确保数据安全隔离")

    conn, c = get_db()
    product = c.execute(
        "SELECT * FROM products WHERE id = ? AND user_id = ?",
        (product_id, user_id)
    ).fetchone()
    return dict(product) if product else None


def delete_product(product_id, user_id):
    """删除产品"""
    conn, c = get_db()
    c.execute(
        "DELETE FROM products WHERE id = ? AND user_id = ?",
        (product_id, user_id)
    )
    conn.commit()
    return c.rowcount > 0


def batch_delete_products(product_ids, user_id):
    """批量删除产品"""
    if not product_ids:
        return 0

    conn, c = get_db()
    placeholders = ','.join(['?' for _ in product_ids])
    params = list(product_ids) + [user_id]

    c.execute(
        f"DELETE FROM products WHERE id IN ({placeholders}) AND user_id = ?",
        params
    )
    conn.commit()
    return c.rowcount


def update_product(product_id, user_id, updates):
    """更新产品信息"""
    if not updates:
        return False

    conn, c = get_db()

    # 构建UPDATE语句
    set_clauses = []
    values = []
    for field, value in updates.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)

    values.extend([product_id, user_id])

    c.execute(
        f"UPDATE products SET {', '.join(set_clauses)} " +
        "WHERE id = ? AND user_id = ?",
        values
    )
    conn.commit()
    return c.rowcount > 0


def batch_update_pricing_params(product_ids, user_id, pricing_updates):
    """批量更新产品定价参数"""
    if not product_ids or not pricing_updates:
        return 0

    conn, c = get_db()

    # 构建UPDATE语句
    set_clauses = []
    values = []
    for field, value in pricing_updates.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)

    placeholders = ','.join(['?' for _ in product_ids])
    values.extend(list(product_ids))
    values.append(user_id)

    c.execute(
        f"UPDATE products SET {', '.join(set_clauses)} " +
        f"WHERE id IN ({placeholders}) AND user_id = ?",
        values
    )
    conn.commit()
    return c.rowcount


def calculate_and_update_priority_groups(user_id):
    """计算并更新物流优先级分组 - 支持用户隔离"""
    conn, c = get_db()

    # 获取指定用户的物流数据
    logistics = c.execute(
        "SELECT id, type, min_days, max_days FROM logistics WHERE user_id = ?",
        (user_id,)
    ).fetchall()

    # 按类型分组
    land_logistics = [log for log in logistics if log['type'] == 'land']
    air_logistics = [log for log in logistics if log['type'] == 'air']

    def calculate_group_averages(logistics_list):
        """计算物流组的平均值"""
        if not logistics_list:
            return 0, 0, 0

        # 过滤出时效不为0的物流（参与平均值计算）
        valid_logistics = [
            log for log in logistics_list
            if log['min_days'] > 0 and log['max_days'] > 0
        ]

        if not valid_logistics:
            return 0, 0, 0

        # 计算平均最快时效(A)
        min_days_sum = sum(log['min_days'] for log in valid_logistics)
        avg_fastest = min_days_sum / len(valid_logistics)

        # 计算平均最慢时效(B)
        max_days_sum = sum(log['max_days'] for log in valid_logistics)
        avg_slowest = max_days_sum / len(valid_logistics)

        # 计算每个物流的平均时效(C)的平均值(D)
        avg_times = []
        for log in valid_logistics:
            avg_time = (log['min_days'] + log['max_days']) / 2
            avg_times.append(avg_time)
        avg_overall = sum(avg_times) / len(avg_times)

        return avg_fastest, avg_slowest, avg_overall

    def assign_priority_group(log, avg_fastest, avg_slowest, avg_overall):
        """为单个物流分配优先级组"""
        min_days = log['min_days']
        max_days = log['max_days']

        # 如果时效为0，分配为E组（优先级最低）
        if min_days == 0 and max_days == 0:
            return 'E'

        avg_time = (min_days + max_days) / 2

        # 计算有多少个值小于平均值
        count_below_avg = 0
        if min_days < avg_fastest:
            count_below_avg += 1
        if max_days < avg_slowest:
            count_below_avg += 1
        if avg_time < avg_overall:
            count_below_avg += 1

        # 根据数量分配组别
        if count_below_avg == 3:
            return 'A'
        elif count_below_avg == 2:
            return 'B'
        elif count_below_avg == 1:
            return 'C'
        else:
            return 'D'

    # 计算陆运组平均值
    land_avg_fastest, land_avg_slowest, land_avg_overall = (
        calculate_group_averages(land_logistics)
    )

    # 计算空运组平均值
    air_avg_fastest, air_avg_slowest, air_avg_overall = (
        calculate_group_averages(air_logistics)
    )

    # 更新陆运物流的优先级组
    for log in land_logistics:
        group = assign_priority_group(
            log, land_avg_fastest, land_avg_slowest, land_avg_overall
        )
        c.execute(
            "UPDATE logistics SET priority_group = ? WHERE id = ?",
            (group, log['id'])
        )

    # 更新空运物流的优先级组
    for log in air_logistics:
        group = assign_priority_group(
            log, air_avg_fastest, air_avg_slowest, air_avg_overall
        )
        c.execute(
            "UPDATE logistics SET priority_group = ? WHERE id = ?",
            (group, log['id'])
        )

    conn.commit()
