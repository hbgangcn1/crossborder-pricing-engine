import streamlit as st
import pandas as pd
import hashlib
from db_utils import get_db


def user_management_page():
    """用户管理页面"""
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
                    hashed = hashlib.sha256(password.encode()).hexdigest()
                    try:
                        c.execute(
                            "INSERT INTO users (username, password, role) "
                            "VALUES (?, ?, ?)",
                            (username, hashed, role),
                        )
                        conn.commit()
                        st.success("用户添加成功！")
                        st.rerun()
                    except Exception:
                        st.error("用户名已存在")
    st.subheader("用户列表")
    users = pd.read_sql("SELECT id, username, role FROM users", conn)
    if users.empty:
        st.info("暂无用户数据")
        return
    choice = st.radio(
        "请选择一名用户",
        options=users.itertuples(index=False),
        format_func=lambda x: f"{x.id} - {x.username} ({x.role})",
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
                            (hashed, user_id),
                        )
                        conn.commit()
                        st.success("密码已更新！")
                        st.rerun()
        if st.button("删除用户", key=f"del_user_{user_id}"):
            if user_id == st.session_state.user["id"]:
                st.error("不能删除当前登录用户")
            else:
                c.execute("DELETE FROM users WHERE id=?", (user_id,))
                conn.commit()
                st.success("用户已删除！")
                st.rerun()


def login_or_register_page():
    """登录/注册页面"""
    st.title("物流定价系统 - 登录 / 注册")
    tab_login, tab_register = st.tabs(["登录", "注册"])
    # 登录
    with tab_login:
        with st.form("login_form"):
            identifier = st.text_input("用户名或邮箱")
            pwd = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")
            if submitted:
                from db_utils import verify_user
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
                import re
                from db_utils import create_user
                if pwd1 != pwd2:
                    st.error("两次密码不一致")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    st.error("邮箱格式不正确")
                elif create_user(username, pwd1, role="user", email=email):
                    st.success("注册成功，请登录")
                else:
                    st.error("用户名或邮箱已注册")
