import time
import secrets
import hashlib
import streamlit as st


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
    def get_client_info():
        """获取客户端信息"""
        # 在实际部署环境中，可以从Streamlit获取真实的客户端信息
        # 这里为了测试简化处理
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
                    locked_until = (
                        time.time() + SessionSecurity.LOCKOUT_DURATION)
                    c.execute("""
                        INSERT OR REPLACE INTO user_lockouts
                        (identifier, locked_until, attempt_count)
                        VALUES (?, ?, ?)
                    """, (identifier, locked_until, failed_attempts))

            conn.commit()

    @staticmethod
    def create_session(user_id: int, user_info: dict) -> str:
        """创建新的用户会话"""
        session_id = SessionSecurity.generate_session_id()
        client_info = SessionSecurity.get_client_info()

        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            # 清理该用户的旧会话
            c.execute(
                "UPDATE active_sessions SET is_active = FALSE "
                "WHERE user_id = ?",
                (user_id,)
            )

            # 创建新会话
            c.execute("""
                INSERT INTO active_sessions
                (session_id, user_id, created_at, last_activity,
                 ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                user_id,
                time.time(),
                time.time(),
                client_info['ip_address'],
                client_info['user_agent']
            ))

            conn.commit()

        # 在Streamlit session_state中存储会话信息
        st.session_state.session_id = session_id
        st.session_state.user = user_info
        st.session_state.last_activity = time.time()

        return session_id

    @staticmethod
    def get_session_info(session_id: str):
        """获取会话信息"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            # 检查会话是否存在且活跃
            session = c.execute("""
                SELECT s.*, u.username, u.email, u.role
                FROM active_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_id = ? AND s.is_active = TRUE
            """, (session_id,)).fetchone()

            if session:
                current_time = time.time()

                # 检查会话是否超时
                if (current_time - session['last_activity'] >
                        SessionSecurity.SESSION_TIMEOUT):
                    # 会话超时，标记为非活跃
                    c.execute(
                        "UPDATE active_sessions SET is_active = FALSE "
                        "WHERE session_id = ?",
                        (session_id,)
                    )
                    conn.commit()
                    return None

                # 更新最后活动时间
                if (current_time - session['last_activity'] >
                        SessionSecurity.SESSION_REFRESH_INTERVAL):
                    c.execute(
                        "UPDATE active_sessions SET last_activity = ? "
                        "WHERE session_id = ?",
                        (current_time, session_id)
                    )
                    conn.commit()

                return {
                    'id': session['user_id'],
                    'username': session['username'],
                    'email': session['email'],
                    'role': session['role'],
                    'session_id': session['session_id'],
                    'last_activity': session['last_activity']
                }

        return None

    @staticmethod
    def invalidate_session(session_id=None):
        """使会话失效"""
        if session_id is None and 'session_id' in st.session_state:
            session_id = st.session_state.session_id

        if session_id:
            from db_utils import get_db_connection
            with get_db_connection() as (conn, c):
                # 标记会话为非活跃
                c.execute(
                    "UPDATE active_sessions SET is_active = FALSE "
                    "WHERE session_id = ?",
                    (session_id,)
                )
                conn.commit()

        # 清理session_state
        for key in ['session_id', 'user', 'last_activity']:
            if key in st.session_state:
                del st.session_state[key]

    @staticmethod
    def cleanup_expired_sessions():
        """清理过期会话"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            # 清理超时的会话
            expired_time = time.time() - SessionSecurity.SESSION_TIMEOUT
            c.execute("""
                UPDATE active_sessions
                SET is_active = FALSE
                WHERE last_activity < ? AND is_active = TRUE
            """, (expired_time,))

            # 清理过期的登录尝试记录（保留24小时）
            old_time = time.time() - 86400
            c.execute(
                "DELETE FROM login_attempts WHERE timestamp < ?",
                (old_time,)
            )

            # 清理过期的用户锁定记录
            c.execute(
                "DELETE FROM user_lockouts WHERE locked_until < ?",
                (time.time(),)
            )

            conn.commit()

    @staticmethod
    def get_user_session_info(user_id: int):
        """获取用户的会话信息"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            session = c.execute("""
                SELECT * FROM active_sessions
                WHERE user_id = ? AND is_active = TRUE
                ORDER BY last_activity DESC LIMIT 1
            """, (user_id,)).fetchone()

            if session:
                return {
                    'session_id': session['session_id'],
                    'created_at': session['created_at'],
                    'last_activity': session['last_activity'],
                    'ip_address': session['ip_address'],
                    'user_agent': session['user_agent']
                }
            return None

    @staticmethod
    def get_active_session_count(user_id: int) -> int:
        """获取用户活跃会话数量"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            return c.execute("""
                SELECT COUNT(*) FROM active_sessions
                WHERE user_id = ? AND is_active = TRUE
            """, (user_id,)).fetchone()[0]

    @staticmethod
    def force_logout_user(user_id: int):
        """强制用户退出所有会话"""
        from db_utils import get_db_connection
        with get_db_connection() as (conn, c):
            c.execute(
                "UPDATE active_sessions SET is_active = FALSE "
                "WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()


def secure_login(username_or_email: str, password: str) -> bool:
    """安全登录函数"""
    from db_utils import verify_user

    # 检查用户是否被锁定
    if SessionSecurity.is_user_locked(username_or_email):
        st.error("账户已被临时锁定，请稍后再试")
        return False

    # 验证用户凭据
    user = verify_user(username_or_email, password)

    if user:
        # 登录成功
        SessionSecurity.record_login_attempt(username_or_email, True)

        # 创建安全会话
        SessionSecurity.create_session(user['id'], user)

        st.success(f"欢迎回来，{user['username']}！")
        return True
    else:
        # 登录失败
        SessionSecurity.record_login_attempt(username_or_email, False)
        st.error("用户名/邮箱或密码错误")
        return False


def secure_logout():
    """安全登出函数"""
    SessionSecurity.invalidate_session()
    st.success("已安全退出")
    st.rerun()  # 触发页面重新加载，返回登录界面


def check_session_security():
    """检查会话安全性"""
    if 'session_id' in st.session_state:
        session_info = SessionSecurity.get_session_info(
            st.session_state.session_id)
        if session_info:
            # 会话有效，更新用户信息
            st.session_state.user = session_info
            return True
        else:
            # 会话无效，清理状态
            SessionSecurity.invalidate_session()

    return False


def show_session_info():
    """显示会话信息（调试用）"""
    if 'user' in st.session_state:
        user_info = SessionSecurity.get_user_session_info(
            st.session_state.user['id'])
        if user_info:
            # 检查是否需要显示锁定警告
            from db_utils import get_db_connection
            with get_db_connection() as (conn, c):
                recent_time = time.time() - SessionSecurity.LOCKOUT_DURATION
                failed_count = c.execute(
                    """SELECT COUNT(*) FROM login_attempts
                       WHERE identifier = ? AND success = FALSE
                       AND timestamp > ?""",
                    (st.session_state.user['username'], recent_time)
                ).fetchone()[0]

                if failed_count > 0:
                    st.sidebar.warning(f"注意：最近有 {failed_count} 次失败登录尝试")

            st.sidebar.info(f"""
            **会话信息**
            - 用户: {st.session_state.user['username']}
            - 会话ID: {user_info['session_id'][:8]}...
            - 最后活动: {time.strftime(
                '%H:%M:%S', time.localtime(user_info['last_activity']))}
            """)
