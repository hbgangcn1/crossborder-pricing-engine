import os
import sys
from unittest.mock import MagicMock
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_st(monkeypatch):
    import streamlit as st
    st.markdown = MagicMock()
    st.subheader = MagicMock()
    st.write = MagicMock()
    st.info = MagicMock()
    st.warning = MagicMock()
    st.error = MagicMock()
    st.success = MagicMock()
    st.form = MagicMock()
    st.form_submit_button = MagicMock(return_value=False)
    st.text_input = MagicMock(return_value="x")
    st.selectbox = MagicMock(side_effect=[["admin", "user"], "user"])  # 兼容多次调用
    st.radio = MagicMock(return_value="追加模式 (保留用户现有规则)")
    st.button = MagicMock(return_value=False)
    st.multiselect = MagicMock(return_value=[])
    st.columns = lambda n: [MagicMock() for _ in range(n)]
    st.expander = MagicMock()
    st.session_state.clear()
    st.session_state["user"] = {"id": 1, "username": "u", "role": "user"}
    return st


def test_user_page_block_for_non_admin(monkeypatch, mock_st):
    from logistics import ui_user as uu

    # 非管理员进入 → 被拒绝
    uu.user_management_page()
    mock_st.error.assert_any_call("❌ 访问被拒绝：您没有管理员权限")


def test_user_delete_self_protection(monkeypatch, mock_st):
    from logistics import ui_user as uu

    # 伪造管理员权限通过
    monkeypatch.setattr(uu, "require_admin", lambda: None)
    # 供页面读取的用户列表（包含当前用户）
    df = pd.DataFrame([{"id": 1, "username": "u", "role": "admin"}])
    
    # Mock pd.read_sql 以避免数据库连接问题
    def mock_read_sql(query, conn=None, params=None):
        if "SELECT id, username FROM users WHERE role != 'admin'" in query:
            return pd.DataFrame([{"id": 2, "username": "other_user"}])
        elif "SELECT id, username, role FROM users" in query:
            return df
        else:
            return pd.DataFrame()
    
    monkeypatch.setattr(pd, "read_sql", mock_read_sql)

    # radio返回itertuples中的第一个
    def _radio(label, options, format_func=None, **kwargs):
        return next(iter(options))
    mock_st.radio = _radio

    # 仅当点击“删除用户”时返回 True，其它按钮一律 False
    def _button(label, *args, **kwargs):
        return label == "删除用户"
    mock_st.button = MagicMock(side_effect=_button)
    uu.user_management_page()

    mock_st.error.assert_any_call("不能删除当前登录用户")


