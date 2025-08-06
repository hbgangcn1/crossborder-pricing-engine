import streamlit as st
import pandas as pd
import hashlib
import sqlite3
from db_utils import get_db


def sync_logistics_rules(target_user_id: int, overwrite: bool = False):
    """
    将admin账号的物流规则同步到指定用户账号
    
    Args:
        target_user_id: 目标用户ID
        overwrite: 是否覆盖模式（删除用户现有规则）
    """
    conn, c = get_db()
    
    try:
        # 获取admin用户ID
        admin_user = c.execute(
            "SELECT id FROM users WHERE role='admin' LIMIT 1"
        ).fetchone()
        
        if not admin_user:
            st.error("找不到admin用户")
            return
            
        admin_id = admin_user[0]
        
        # 如果是覆盖模式，先删除目标用户的现有物流规则
        if overwrite:
            c.execute("DELETE FROM logistics WHERE user_id = ?", (target_user_id,))
        
        # 获取admin的所有物流规则
        admin_logistics = c.execute(
            "SELECT * FROM logistics WHERE user_id = ?", (admin_id,)
        ).fetchall()
        
        # 获取logistics表的所有列名（除了id和user_id）
        columns_info = c.execute("PRAGMA table_info(logistics)").fetchall()
        columns = [col[1] for col in columns_info if col[1] not in ['id', 'user_id']]
        
        # 复制每条物流规则到目标用户
        for logistics_rule in admin_logistics:
            # 构建INSERT语句
            placeholders = ','.join(['?' for _ in columns])
            columns_str = ','.join(columns)
            
            # 准备数据（排除id和user_id列）
            values = []
            for col in columns:
                # 根据列名获取对应的值
                col_index = [info[1] for info in columns_info].index(col)
                values.append(logistics_rule[col_index])
            
            # 插入新记录
            c.execute(
                f"INSERT INTO logistics (user_id, {columns_str}) VALUES (?, {placeholders})",
                [target_user_id] + values
            )
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        st.error(f"同步失败: {str(e)}")
        raise


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
                    except sqlite3.IntegrityError:
                        st.error("用户名已存在")
                    except Exception as e:
                        st.error(f"添加用户失败: {e}")
    # 批量同步功能
    with st.expander("📦 批量物流规则同步", expanded=False):
        st.write("一键将admin物流规则同步到多个用户账号")
        
        # 获取所有非admin用户
        non_admin_users = pd.read_sql(
            "SELECT id, username FROM users WHERE role != 'admin'", conn
        )
        
        if not non_admin_users.empty:
            # 显示admin的物流规则数量
            admin_logistics_count = c.execute(
                "SELECT COUNT(*) FROM logistics WHERE user_id = "
                "(SELECT id FROM users WHERE role='admin' LIMIT 1)"
            ).fetchone()[0]
            
            st.info(f"Admin物流规则数量: {admin_logistics_count}")
            
            if admin_logistics_count > 0:
                # 多选用户
                selected_users = st.multiselect(
                    "选择要同步的用户:",
                    options=non_admin_users['id'].tolist(),
                    format_func=lambda x: non_admin_users[
                        non_admin_users['id'] == x]['username'].iloc[0],
                    key="batch_sync_users"
                )
                
                # 同步选项
                batch_sync_mode = st.radio(
                    "批量同步方式:",
                    ["追加模式 (保留用户现有规则)", "覆盖模式 (删除用户现有规则)"],
                    key="batch_sync_mode"
                )
                
                if st.button("🚀 批量同步物流规则") and selected_users:
                    success_count = 0
                    failed_users = []
                    
                    for user_id in selected_users:
                        try:
                            sync_logistics_rules(
                                user_id, 
                                batch_sync_mode == "覆盖模式 (删除用户现有规则)"
                            )
                            success_count += 1
                        except Exception as e:
                            username = non_admin_users[
                                non_admin_users['id'] == user_id]['username'].iloc[0]
                            failed_users.append(f"{username}: {str(e)}")
                    
                    if success_count > 0:
                        st.success(f"成功同步到 {success_count} 个用户账号")
                    
                    if failed_users:
                        st.error("以下用户同步失败:")
                        for error in failed_users:
                            st.write(f"- {error}")
                    
                    if success_count > 0:
                        st.rerun()
            else:
                st.warning("Admin账号没有物流规则可同步")
        else:
            st.info("没有可同步的用户账号")
    
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
        # 物流规则同步功能
        with st.expander("物流规则同步"):
            st.write("将admin账号的物流规则同步到此用户账号")
            
            # 显示admin的物流规则数量
            admin_logistics_count = c.execute(
                "SELECT COUNT(*) FROM logistics WHERE user_id = "
                "(SELECT id FROM users WHERE role='admin' LIMIT 1)"
            ).fetchone()[0]
            
            # 显示目标用户的物流规则数量
            user_logistics_count = c.execute(
                "SELECT COUNT(*) FROM logistics WHERE user_id = ?", 
                (user_id,)
            ).fetchone()[0]
            
            st.info(f"Admin物流规则数量: {admin_logistics_count}")
            st.info(f"{choice.username}当前物流规则数量: {user_logistics_count}")
            
            # 同步选项
            sync_mode = st.radio(
                "同步方式:",
                ["追加模式 (保留用户现有规则)", "覆盖模式 (删除用户现有规则)"],
                key=f"sync_mode_{user_id}"
            )
            
            if st.button("🔄 同步物流规则", key=f"sync_logistics_{user_id}"):
                if admin_logistics_count == 0:
                    st.warning("Admin账号没有物流规则可同步")
                else:
                    sync_logistics_rules(user_id, sync_mode == "覆盖模式 (删除用户现有规则)")
                    st.success(f"成功同步 {admin_logistics_count} 条物流规则到 {choice.username}")
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
    """登录页面"""
    st.title("物流定价系统 - 登录")
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
