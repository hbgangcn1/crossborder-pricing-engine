#!/usr/bin/env python3
"""
会话安全管理模块
提供完整的用户会话安全功能
"""
import time
import hashlib
import secrets
import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime


class SessionSecurity:
    """会话安全管理类"""

    # 配置常量
    SESSION_TIMEOUT = 7200  # 2小时超时
    MAX_LOGIN_ATTEMPTS = 5  # 最大登录尝试次数
    LOCKOUT_DURATION = 900  # 15分钟锁定时间
    SESSION_REFRESH_INTERVAL = 300  # 5分钟刷新间隔

    @staticmethod
    def init_session_tables():
        """初始化会话相关数据表"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            # 创建登录尝试记录表
            c.execute("""
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier TEXT NOT NULL,
                    ip_address TEXT,
                    timestamp REAL NOT NULL,
                    success BOOLEAN NOT NULL,
                    user_agent TEXT
                )
            """)

            # 创建活动会话表
            c.execute("""
                CREATE TABLE IF NOT EXISTS active_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    last_activity REAL NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # 创建用户锁定表
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_lockouts (
                    identifier TEXT PRIMARY KEY,
                    locked_until REAL NOT NULL,
                    attempt_count INTEGER NOT NULL
                )
            """)

            conn.commit()

    @staticmethod
    def generate_session_id() -> str:
        """生成安全的会话ID"""
        # 使用时间戳 + 随机数 + 用户信息生成唯一会话ID
        timestamp = str(time.time())
        random_bytes = secrets.token_bytes(32)
        session_data = timestamp + random_bytes.hex()
        return hashlib.sha256(session_data.encode()).hexdigest()

    @staticmethod
    def get_client_info() -> Dict[str, str]:
        """获取客户端信息（模拟）"""
        # 在真实环境中，可以从HTTP头获取更多信息
        return {
            'ip_address': 'localhost',  # 本地开发环境
            'user_agent': 'Streamlit/1.48.0'
        }

    @staticmethod
    def is_user_locked(identifier: str) -> bool:
        """检查用户是否被锁定"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            lockout = c.execute(
                "SELECT locked_until FROM user_lockouts WHERE identifier = ?",
                (identifier,)
            ).fetchone()

            if lockout:
                if time.time() < lockout[0]:
                    return True
                else:
                    # 锁定时间已过，移除锁定记录
                    c.execute(
                        "DELETE FROM user_lockouts WHERE identifier = ?",
                        (identifier,)
                    )
                    conn.commit()

            return False

    @staticmethod
    def record_login_attempt(identifier: str, success: bool):
        """记录登录尝试"""
        from db_utils import get_db_connection

        client_info = SessionSecurity.get_client_info()
        with get_db_connection() as (conn, c):
            # 记录登录尝试
            c.execute("""
                INSERT INTO login_attempts
                (identifier, ip_address, timestamp, success, user_agent)
                VALUES (?, ?, ?, ?, ?)
            """, (
                identifier,
                client_info['ip_address'],
                time.time(),
                success,
                client_info['user_agent']
            ))

            if not success:
                # 统计最近的失败次数
                recent_time = time.time() - SessionSecurity.LOCKOUT_DURATION
                failed_attempts = c.execute("""
                    SELECT COUNT(*) FROM login_attempts
                WHERE identifier = ? AND success = FALSE AND timestamp > ?
            """, (identifier, recent_time)).fetchone()[0]

            if failed_attempts >= SessionSecurity.MAX_LOGIN_ATTEMPTS:
                # 锁定用户
                locked_until = time.time() + SessionSecurity.LOCKOUT_DURATION
                c.execute("""
                    INSERT OR REPLACE INTO user_lockouts
                    (identifier, locked_until, attempt_count)
                    VALUES (?, ?, ?)
                """, (identifier, locked_until, failed_attempts))

        conn.commit()

    @staticmethod
    def create_session(user: Dict[str, Any]) -> str:
        """创建新的安全会话"""
        from db_utils import get_db

        session_id = SessionSecurity.generate_session_id()
        current_time = time.time()
        client_info = SessionSecurity.get_client_info()

        conn, c = get_db()

        # 清理该用户的旧会话
        c.execute(
            "UPDATE active_sessions SET is_active = FALSE WHERE user_id = ?",
            (user['id'],)
        )

        # 创建新会话
        c.execute("""
            INSERT INTO active_sessions
            (session_id, user_id, created_at, last_activity,
             ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            user['id'],
            current_time,
            current_time,
            client_info['ip_address'],
            client_info['user_agent']
        ))

        conn.commit()

        # 设置会话状态
        st.session_state.user = user
        st.session_state.session_id = session_id
        st.session_state.login_time = current_time
        st.session_state.last_activity = current_time

        return session_id

    @staticmethod
    def validate_session() -> bool:
        """验证当前会话是否有效"""
        if 'user' not in st.session_state or st.session_state.user is None:
            return False

        if 'session_id' not in st.session_state:
            return False

        from db_utils import get_db
        conn, c = get_db()

        # 检查会话是否存在且活跃
        session = c.execute("""
            SELECT user_id, created_at, last_activity, is_active
            FROM active_sessions
            WHERE session_id = ? AND is_active = TRUE
        """, (st.session_state.session_id,)).fetchone()

        if not session:
            return False

        current_time = time.time()

        # 检查会话是否超时
        if current_time - session[2] > SessionSecurity.SESSION_TIMEOUT:
            SessionSecurity.destroy_session()
            return False

        # 检查是否需要刷新活动时间
        if (current_time - session[2] >
                SessionSecurity.SESSION_REFRESH_INTERVAL):
            c.execute("""
                UPDATE active_sessions
                SET last_activity = ?
                WHERE session_id = ?
            """, (current_time, st.session_state.session_id))
            conn.commit()
            st.session_state.last_activity = current_time

        return True

    @staticmethod
    def destroy_session():
        """销毁当前会话"""
        if 'session_id' in st.session_state:
            from db_utils import get_db
            conn, c = get_db()

            # 标记会话为非活跃
            c.execute(
                "UPDATE active_sessions SET is_active = FALSE " +
                "WHERE session_id = ?",
                (st.session_state.session_id,)
            )
            conn.commit()

        # 清理session_state
        keys_to_remove = [
            'user', 'session_id', 'login_time', 'last_activity',
            'products_data', 'logistics_data', 'edit_product_id',
            'batch_edit_products', 'delete_confirm_product_id',
            'batch_delete_products'
        ]

        for key in keys_to_remove:
            if key in st.session_state:
                del st.session_state[key]

    @staticmethod
    def cleanup_old_sessions():
        """清理过期会话"""
        from db_utils import get_db
        conn, c = get_db()

        # 清理超时的会话
        timeout_threshold = time.time() - SessionSecurity.SESSION_TIMEOUT
        c.execute("""
            UPDATE active_sessions
            SET is_active = FALSE
            WHERE last_activity < ? AND is_active = TRUE
        """, (timeout_threshold,))

        # 清理旧的登录尝试记录（保留30天）
        old_attempts_threshold = time.time() - (30 * 24 * 3600)
        c.execute(
            "DELETE FROM login_attempts WHERE timestamp < ?",
            (old_attempts_threshold,)
        )

        # 清理过期的锁定记录
        c.execute(
            "DELETE FROM user_lockouts WHERE locked_until < ?",
            (time.time(),)
        )

        conn.commit()

    @staticmethod
    def get_session_info() -> Optional[Dict[str, Any]]:
        """获取当前会话信息"""
        if not SessionSecurity.validate_session():
            return None

        from db_utils import get_db
        conn, c = get_db()

        session = c.execute("""
            SELECT s.session_id, s.user_id, s.created_at, s.last_activity,
                   s.ip_address, s.user_agent, u.username, u.role
            FROM active_sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_id = ? AND s.is_active = TRUE
        """, (st.session_state.session_id,)).fetchone()

        if session:
            return {
                'session_id': session[0],
                'user_id': session[1],
                'created_at': datetime.fromtimestamp(session[2]),
                'last_activity': datetime.fromtimestamp(session[3]),
                'ip_address': session[4],
                'user_agent': session[5],
                'username': session[6],
                'role': session[7],
                'session_duration': time.time() - session[2],
                'time_since_last_activity': time.time() - session[3]
            }

        return None

    @staticmethod
    def get_active_sessions_count(user_id: int) -> int:
        """获取用户活跃会话数量"""
        from db_utils import get_db
        conn, c = get_db()

        return c.execute("""
            SELECT COUNT(*) FROM active_sessions
            WHERE user_id = ? AND is_active = TRUE
        """, (user_id,)).fetchone()[0]

    @staticmethod
    def force_logout_user(user_id: int):
        """强制用户退出所有会话"""
        from db_utils import get_db
        conn, c = get_db()

        c.execute(
            "UPDATE active_sessions SET is_active = FALSE WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()


def init_session_security():
    """初始化会话安全功能"""
    SessionSecurity.init_session_tables()
    SessionSecurity.cleanup_old_sessions()


def check_session_security():
    """检查会话安全性（在每个页面调用）"""
    # 初始化会话表（如果需要）
    if 'session_security_initialized' not in st.session_state:
        init_session_security()
        st.session_state.session_security_initialized = True

    # 验证会话
    if not SessionSecurity.validate_session():
        if 'user' in st.session_state and st.session_state.user is not None:
            # 会话无效但用户信息存在，显示超时消息
            st.error("🔒 会话已超时，请重新登录")
            SessionSecurity.destroy_session()
            time.sleep(1)  # 给用户时间看到消息
            st.rerun()
        return False

    return True


def secure_login(identifier: str, password: str) -> Optional[Dict[str, Any]]:
    """安全登录功能"""
    # 检查用户是否被锁定
    if SessionSecurity.is_user_locked(identifier):
        remaining_time = SessionSecurity.LOCKOUT_DURATION / 60
        st.error(f"🔒 账户已被锁定，请在 {remaining_time:.0f} 分钟后重试")
        return None

    # 验证用户
    from db_utils import verify_user
    user = verify_user(identifier, password)

    # 记录登录尝试
    SessionSecurity.record_login_attempt(identifier, user is not None)

    if user:
        # 创建安全会话
        SessionSecurity.create_session(user)
        return user
    else:
        # 检查是否需要显示锁定警告
        from db_utils import get_db
        conn, c = get_db()

        recent_time = time.time() - SessionSecurity.LOCKOUT_DURATION
        failed_attempts = c.execute("""
            SELECT COUNT(*) FROM login_attempts
            WHERE identifier = ? AND success = FALSE AND timestamp > ?
        """, (identifier, recent_time)).fetchone()[0]

        remaining_attempts = (SessionSecurity.MAX_LOGIN_ATTEMPTS -
                              failed_attempts)
        if remaining_attempts <= 2:
            st.warning(f"⚠️ 还有 {remaining_attempts} 次尝试机会，之后账户将被锁定")

        return None


def secure_logout():
    """安全退出功能"""
    SessionSecurity.destroy_session()
    st.success("✅ 已安全退出")
    time.sleep(1)
    st.rerun()
