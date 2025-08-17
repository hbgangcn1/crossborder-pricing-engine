import streamlit as st
import pandas as pd
import sqlite3
import requests
import time

try:
    from .logic import calculate_pricing
except ImportError:
    from logic import calculate_pricing
try:
    from .db_utils import (
        get_db,
        current_user_id,
        check_user_subscription_status,
        decrement_user_calculations,
    )
except ImportError:
    from db_utils import (
        get_db,
        current_user_id,
        check_user_subscription_status,
        decrement_user_calculations,
    )


def format_logistics_name(name: str, delivery_method: str, include_delivery: bool = True) -> str:
    """
    格式化物流名称
    
    Args:
        name: 原始物流名称
        delivery_method: 送货方式
        include_delivery: 是否包含送货方式（True用于显示，False用于编辑）
    
    Returns:
        格式化后的物流名称
    """
    if not include_delivery:
        return name
    
    delivery_method_map = {
        "home_delivery": "送货上门",
        "pickup_point": "送货到取货点",
        "unknown": "未知",
    }
    
    delivery_display = delivery_method_map.get(delivery_method, "未知")
    return f"{name} {delivery_display}"


def _render_pricing_card(
    grad_start: str,
    grad_end: str,
    border_color: str,
    shadow_rgba: str,
    best_name: str,
    cost_display: str,
    time_display: str,
    price: float,
    expected_profit: float,
    profit_margin: float,
    avg_cost: float,
    cost_saving: float,
    avg_time: float,
    time_saving_display: str,
) -> str:
    parts: list[str] = [
        "<div style='background: linear-gradient(135deg,",
        f"{grad_start} 0%, ",
        f"{grad_end} 100%); ",
        "border-radius:12px; padding:16px; margin:8px 0; ",
        f"border-left:4px solid {border_color}; ",
        f"box-shadow:0 4px 12px {shadow_rgba};'>",
        "<div style='font-size:1.6em; color:#2c3e50; ",
        "font-weight:800; margin-bottom:8px;'>最佳物流：",
        f"{best_name}</div>",
        "<div>运费：<span style='color:#e74c3c; font-weight:600;'>",
        f"{cost_display}</span></div>",
        "<div>时效：<span style='font-weight:600;'>",
        f"{time_display}</span></div>",
        "<hr style='margin:10px 0; border:none; ",
        "border-top:2px solid rgba(52,73,94,0.2);'>",
        "<div style='font-size:1.6em; font-weight:800;'>建议售价：",
        "<span style='color:#e74c3c; font-weight:800; ",
        "font-size:1.6em;'>",
        f"¥{price:.2f}</span></div>",
        "<div>预期利润：<span style='color:#27ae60; font-weight:600;'>",
        f"¥{expected_profit:.2f}</span></div>",
        "<div>利润率：<span style='color:#27ae60; font-weight:600;'>",
        f"{profit_margin:.1f}%</span></div>",
        "<hr style='margin:10px 0; border:none; ",
        "border-top:2px solid rgba(52,73,94,0.2);'>",
        "<div>平均运费：<span style='font-weight:600;'>",
        f"¥{avg_cost:.2f}</span></div>",
        "<div>节省运费：<span style='color:#27ae60; font-weight:600;'>",
        f"{cost_saving:+.1f}%</span></div>",
        "<div>平均时效：<span style='font-weight:600;'>",
        f"{avg_time:.1f}天</span></div>",
        "<div>节省时效：<span style='color:#27ae60; font-weight:600;'>",
        f"{time_saving_display}</span></div>",
        "</div>",
    ]
    return "".join(parts)


def pricing_calculator_page():
    """定价计算器页面"""
    # 检查用户订阅状态
    user_id = current_user_id()
    if not check_user_subscription_status(user_id).get("valid", False):
        st.error("账号到期，请联系客服续费")
        return

    # 美化页面标题
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 class="main-title">💰 定价计算器</h1>
            <p style="color: #718096; font-size: 1.1rem; margin: 0;">
                智能计算产品定价，一键筛选最佳物流
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 显示汇率信息
    try:
        from .exchange_service import ExchangeRateService
    except ImportError:
        from exchange_service import ExchangeRateService

    # 初始化汇率变量 - 使用缓存避免重复请求
    current_rate = 0.0904  # 默认兜底汇率

    # 使用session state缓存汇率，避免重复请求
    if "cached_exchange_rate" not in st.session_state:
        try:
            exchange_service = ExchangeRateService()
            current_rate = exchange_service.get_exchange_rate()
            st.session_state.cached_exchange_rate = current_rate
            st.session_state.cached_exchange_rate_time = time.time()
        except (requests.RequestException, ValueError) as e:
            st.sidebar.warning(f"汇率获取失败: {str(e)}")
            st.session_state.cached_exchange_rate = current_rate
            st.session_state.cached_exchange_rate_time = time.time()
    else:
        # 检查缓存是否过期（5分钟）
        cache_age = time.time() - st.session_state.cached_exchange_rate_time
        if cache_age > 300:  # 5分钟过期
            try:
                exchange_service = ExchangeRateService()
                current_rate = exchange_service.get_exchange_rate()
                st.session_state.cached_exchange_rate = current_rate
                st.session_state.cached_exchange_rate_time = time.time()
            except (requests.RequestException, ValueError) as e:
                st.sidebar.warning(f"汇率更新失败: {str(e)}")
                current_rate = st.session_state.cached_exchange_rate
        else:
            current_rate = st.session_state.cached_exchange_rate

    st.sidebar.success(f"当前汇率: 1 CNY = {current_rate:.2f} RUB")

    conn, cursor = get_db()
    uid = current_user_id()

    # 获取用户的产品列表
    products = pd.read_sql(
        "SELECT id, name, category FROM products WHERE user_id = ?",
        conn,
        params=(uid,),
    )

    if products.empty:
        st.warning("请先添加产品")
        _close_conn_if_sqlite(conn)
        return

    # 产品选择
    st.markdown(
        (
            '<h3 style="color: #2c3e50; margin-bottom: 20px; '
            "font-size: 1.5em; font-weight: 600; "
            "border-bottom: 2px solid #3498db; "
            'padding-bottom: 8px;">📦 产品选择</h3>'
        ),
        unsafe_allow_html=True,
    )

    selected_product_name = st.selectbox(
        "选择产品", products["name"].tolist(), key="product_select"
    )

    if not selected_product_name:
        st.info("请选择一个产品")
        _close_conn_if_sqlite(conn)
        return

    # 获取选中产品的详细信息
    product_df = pd.read_sql(
        "SELECT * FROM products WHERE name = ? AND user_id = ?",
        conn,
        params=(selected_product_name, uid),
    )

    if product_df.empty:
        st.error("未找到选中的产品")
        _close_conn_if_sqlite(conn)
        return

    product_series = product_df.iloc[0]

    # 转换为字典，确保所有字段都有默认值
    product = {}
    for column in product_series.index:
        value = product_series[column]
        # 处理None值，为数值字段提供默认值
        if pd.isna(value):
            if (
                "price" in column.lower()
                or "fee" in column.lower()
                or "rate" in column.lower()
            ):
                product[column] = 0.0
            elif (
                "weight" in column.lower()
                or "length" in column.lower()
                or "width" in column.lower()
                or "height" in column.lower()
            ):
                product[column] = 0
            elif "has_" in column.lower() or "is_" in column.lower():
                product[column] = 0
            else:
                product[column] = ""
        else:
            product[column] = value

    # 计算按钮
    st.markdown(
        '<h3 style="color: #2c3e50; margin-bottom: 20px; font-size: 1.5em; '
        "font-weight: 600; border-bottom: 2px solid #3498db; "
        'padding-bottom: 8px;">🚀 开始计算</h3>',
        unsafe_allow_html=True,
    )

    # 计算按钮
    if st.button("🚀 开始计算", key="calculate_button"):
        # 检查计算次数限制
        sub_status = check_user_subscription_status(user_id)
        if not sub_status.get("valid", False):
            st.error("账号到期，请联系客服续费")
            _close_conn_if_sqlite(conn)
            return
        if not decrement_user_calculations(user_id):
            st.error("计算次数已用尽，请联系客服续费")
            _close_conn_if_sqlite(conn)
            return

        # 显示进度提示
        with st.spinner("正在计算定价，请稍候..."):
            # 获取物流数据
            logistics_query = "SELECT * FROM logistics WHERE user_id = ?"
            logistics_df = pd.read_sql(logistics_query, conn, params=(uid,))

            if logistics_df.empty:
                st.error("请先添加物流规则")
                _close_conn_if_sqlite(conn)
                return

            # 分离陆运和空运物流
            land_logistics = logistics_df[logistics_df["type"] == "land"]
            air_logistics = logistics_df[logistics_df["type"] == "air"]

            # 预先计算所有物流成本，避免重复计算
            progress_container = st.empty()
            progress_container.info("正在分析物流规则...")

            # 计算定价 - 使用低价优先（只计算一次，后续复用结果）
            pricing_result = calculate_pricing(
                product, land_logistics, air_logistics, "低价优先"
            )

            # 计算速度优先结果
            progress_container.info("正在计算速度优先方案...")
            pricing_result_speed = calculate_pricing(
                product, land_logistics, air_logistics, "速度优先"
            )

            # 清除进度消息
            progress_container.empty()

        # 显示结果
        st.markdown(
            (
                '<h3 style="color: #2c3e50; margin-bottom: 20px; '
                "font-size: 1.5em; font-weight: 600; "
                "border-bottom: 2px solid #3498db; "
                'padding-bottom: 8px;">📊 计算结果</h3>'
            ),
            unsafe_allow_html=True,
        )

        # 产品信息
        st.markdown(
            (
                '<h4 style="color: #34495e; margin-bottom: 15px; '
                'font-size: 1.2em; font-weight: 600;">📦 产品信息</h4>'
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            (
                '<div style="background: linear-gradient(135deg, '
                "#f8f9fa 0%, #e9ecef 100%); border-radius: 12px; "
                "padding: 20px; margin: 15px 0; "
                'border-left: 4px solid #28a745;">'
                '<div style="font-size: 1.1em; color: #2c3e50; '
                'margin-bottom: 8px;"><strong>产品名称：</strong>'
                f"{product['name']}</div>"
                '<div style="font-size: 1.1em; color: #2c3e50; '
                'margin-bottom: 8px;"><strong>产品类别：</strong>'
                f"{product['category']}</div>"
                '<div style="font-size: 1.1em; color: #2c3e50;">'
                f"<strong>重量：</strong>{product['weight_g']}g</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        # 定价结果 - 低价优先显示
        st.markdown(
            (
                '<h3 style="color: #2c3e50; margin-bottom: 20px; '
                "font-size: 1.5em; font-weight: 600; "
                "border-bottom: 2px solid #3498db; "
                'padding-bottom: 8px;">💰 低价优先</h3>'
            ),
            unsafe_allow_html=True,
        )

        # 创建左右两列布局（陆运 / 空运）
        col_land, col_air = st.columns(2)

        # ------- 陆运：送到取货点 + 送货上门 -------
        with col_land:
            st.markdown(
                (
                    '<h4 style="color: #2c3e50; margin-bottom: 10px; '
                    'font-size: 1.2em; font-weight: 600;">🚛 陆运</h4>'
                ),
                unsafe_allow_html=True,
            )

            # 送到取货点（陆运）
            st.markdown(
                (
                    '<div style="font-weight:700; margin:6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🏬 送到取货点</div>'
                ),
                unsafe_allow_html=True,
            )
            land_is_df = isinstance(land_logistics, pd.DataFrame)
            land_empty = getattr(land_logistics, "empty", True)
            land_cols = list(getattr(land_logistics, "columns", []))
            if (
                land_is_df
                and (not land_empty)
                and ("delivery_method" in land_cols)
            ):
                land_pickup = land_logistics.loc[
                    land_logistics["delivery_method"] == "pickup_point"
                ].copy()
            else:
                land_pickup = pd.DataFrame()
            if not land_pickup.empty:
                res_lp = calculate_pricing(
                    product,
                    land_pickup,
                    pd.DataFrame(),
                    "低价优先",
                )
                best = res_lp.get("best_land") or {}
                cost = res_lp.get("land_cost")
                price = res_lp.get("land_price") or 0
                stats = res_lp.get("land_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                # 预期利润（与logic一致的基于总成本的表达）
                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )

                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                # 格式化物流名称（显示时包含送货方式）
                formatted_best_name = format_logistics_name(
                    best.get("name", ""),
                    best.get("delivery_method", "unknown"),
                    include_delivery=True
                )
                
                html = _render_pricing_card(
                    grad_start="#e3f2fd",
                    grad_end="#bbdefb",
                    border_color="#2196f3",
                    shadow_rgba="rgba(33,150,243,0.15)",
                    best_name=formatted_best_name,
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送到取货点陆运方案")

            # 送货上门（陆运）
            st.markdown(
                (
                    '<div style="font-weight:700; margin:12px 0 6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🚪 送货上门</div>'
                ),
                unsafe_allow_html=True,
            )
            land_is_df = isinstance(land_logistics, pd.DataFrame)
            land_empty = getattr(land_logistics, "empty", True)
            land_cols = list(getattr(land_logistics, "columns", []))
            if (
                land_is_df
                and (not land_empty)
                and ("delivery_method" in land_cols)
            ):
                land_home = land_logistics.loc[
                    land_logistics["delivery_method"] == "home_delivery"
                ].copy()
            else:
                land_home = pd.DataFrame()
            if not land_home.empty:
                res_lh = calculate_pricing(
                    product,
                    land_home,
                    pd.DataFrame(),
                    "低价优先",
                )
                best = res_lh.get("best_land") or {}
                cost = res_lh.get("land_cost")
                price = res_lh.get("land_price") or 0
                stats = res_lh.get("land_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                # 格式化物流名称（显示时包含送货方式）
                formatted_best_name = format_logistics_name(
                    best.get("name", ""),
                    best.get("delivery_method", "unknown"),
                    include_delivery=True
                )

                html = _render_pricing_card(
                    grad_start="#e8f5e8",
                    grad_end="#c8e6c9",
                    border_color="#4caf50",
                    shadow_rgba="rgba(76,175,80,0.15)",
                    best_name=formatted_best_name,
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送货上门陆运方案")

        # ------- 空运：送到取货点 + 送货上门 -------
        with col_air:
            st.markdown(
                (
                    '<h4 style="color: #2c3e50; margin-bottom: 10px; '
                    'font-size: 1.2em; font-weight: 600;">✈️ 空运</h4>'
                ),
                unsafe_allow_html=True,
            )

            # 送到取货点（空运）
            st.markdown(
                (
                    '<div style="font-weight:700; margin:6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🏬 送到取货点</div>'
                ),
                unsafe_allow_html=True,
            )
            air_is_df = isinstance(air_logistics, pd.DataFrame)
            air_empty = getattr(air_logistics, "empty", True)
            air_cols = list(getattr(air_logistics, "columns", []))
            if (
                air_is_df
                and (not air_empty)
                and ("delivery_method" in air_cols)
            ):
                air_pickup = air_logistics.loc[
                    air_logistics["delivery_method"] == "pickup_point"
                ].copy()
            else:
                air_pickup = pd.DataFrame()
            if not air_pickup.empty:
                res_ap = calculate_pricing(
                    product,
                    pd.DataFrame(),
                    air_pickup,
                    "低价优先",
                )
                best = res_ap.get("best_air") or {}
                cost = res_ap.get("air_cost")
                price = res_ap.get("air_price") or 0
                stats = res_ap.get("air_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                # 格式化物流名称（显示时包含送货方式）
                formatted_best_name = format_logistics_name(
                    best.get("name", ""),
                    best.get("delivery_method", "unknown"),
                    include_delivery=True
                )

                html = _render_pricing_card(
                    grad_start="#fff3e0",
                    grad_end="#ffe0b2",
                    border_color="#ff9800",
                    shadow_rgba="rgba(255,152,0,0.15)",
                    best_name=formatted_best_name,
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送到取货点空运方案")

            # 送货上门（空运）
            st.markdown(
                (
                    '<div style="font-weight:700; margin:12px 0 6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🚪 送货上门</div>'
                ),
                unsafe_allow_html=True,
            )
            air_is_df = isinstance(air_logistics, pd.DataFrame)
            air_empty = getattr(air_logistics, "empty", True)
            air_cols = list(getattr(air_logistics, "columns", []))
            if (
                air_is_df
                and (not air_empty)
                and ("delivery_method" in air_cols)
            ):
                air_home = air_logistics.loc[
                    air_logistics["delivery_method"] == "home_delivery"
                ].copy()
            else:
                air_home = pd.DataFrame()
            if not air_home.empty:
                res_ah = calculate_pricing(
                    product,
                    pd.DataFrame(),
                    air_home,
                    "低价优先",
                )
                best = res_ah.get("best_air") or {}
                cost = res_ah.get("air_cost")
                price = res_ah.get("air_price") or 0
                stats = res_ah.get("air_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                html = _render_pricing_card(
                    grad_start="#f3e5f5",
                    grad_end="#e1bee7",
                    border_color="#9c27b0",
                    shadow_rgba="rgba(156,39,176,0.15)",
                    best_name=format_logistics_name(best.get("name", ""), best.get("delivery_method", "unknown"), include_delivery=True),
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送货上门空运方案")

        # =============================
        # 速度优先
        # =============================
        st.markdown(
            (
                '<h3 style="color: #2c3e50; margin: 24px 0 12px 0; '
                "font-size: 1.5em; font-weight: 600; "
                "border-bottom: 2px solid #3498db; "
                'padding-bottom: 8px;">⚡ 速度优先</h3>'
            ),
            unsafe_allow_html=True,
        )

        col_land_s, col_air_s = st.columns(2)

        # ------- 陆运（速度优先）：送到取货点 + 送货上门 -------
        with col_land_s:
            st.markdown(
                (
                    '<h4 style="color: #2c3e50; margin-bottom: 10px; '
                    'font-size: 1.2em; font-weight: 600;">🚛 陆运</h4>'
                ),
                unsafe_allow_html=True,
            )

            st.markdown(
                (
                    '<div style="font-weight:700; margin:6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🏬 送到取货点</div>'
                ),
                unsafe_allow_html=True,
            )
            land_is_df = isinstance(land_logistics, pd.DataFrame)
            land_empty = getattr(land_logistics, "empty", True)
            land_cols = list(getattr(land_logistics, "columns", []))
            if (
                land_is_df
                and (not land_empty)
                and ("delivery_method" in land_cols)
            ):
                land_pickup = land_logistics.loc[
                    land_logistics["delivery_method"] == "pickup_point"
                ].copy()
            else:
                land_pickup = pd.DataFrame()
            if not land_pickup.empty:
                res_lp = calculate_pricing(
                    product,
                    land_pickup,
                    pd.DataFrame(),
                    "速度优先",
                )
                best = res_lp.get("best_land") or {}
                cost = res_lp.get("land_cost")
                price = res_lp.get("land_price") or 0
                stats = res_lp.get("land_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                html = _render_pricing_card(
                    grad_start="#e3f2fd",
                    grad_end="#bbdefb",
                    border_color="#2196f3",
                    shadow_rgba="rgba(33,150,243,0.15)",
                    best_name=format_logistics_name(best.get("name", ""), best.get("delivery_method", "unknown"), include_delivery=True),
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送到取货点陆运方案（速度优先）")

            st.markdown(
                (
                    '<div style="font-weight:700; margin:12px 0 6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🚪 送货上门</div>'
                ),
                unsafe_allow_html=True,
            )
            land_is_df = isinstance(land_logistics, pd.DataFrame)
            land_empty = getattr(land_logistics, "empty", True)
            land_cols = list(getattr(land_logistics, "columns", []))
            if (
                land_is_df
                and (not land_empty)
                and ("delivery_method" in land_cols)
            ):
                land_home = land_logistics.loc[
                    land_logistics["delivery_method"] == "home_delivery"
                ].copy()
            else:
                land_home = pd.DataFrame()
            if not land_home.empty:
                res_lh = calculate_pricing(
                    product,
                    land_home,
                    pd.DataFrame(),
                    "速度优先",
                )
                best = res_lh.get("best_land") or {}
                cost = res_lh.get("land_cost")
                price = res_lh.get("land_price") or 0
                stats = res_lh.get("land_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                # 格式化物流名称（显示时包含送货方式）
                formatted_best_name = format_logistics_name(
                    best.get("name", ""),
                    best.get("delivery_method", "unknown"),
                    include_delivery=True
                )

                html = _render_pricing_card(
                    grad_start="#e8f5e8",
                    grad_end="#c8e6c9",
                    border_color="#4caf50",
                    shadow_rgba="rgba(76,175,80,0.15)",
                    best_name=formatted_best_name,
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送货上门陆运方案（速度优先）")

        # ------- 空运（速度优先）：送到取货点 + 送货上门 -------
        with col_air_s:
            st.markdown(
                (
                    '<h4 style="color: #2c3e50; margin-bottom: 10px; '
                    'font-size: 1.2em; font-weight: 600;">✈️ 空运</h4>'
                ),
                unsafe_allow_html=True,
            )

            st.markdown(
                (
                    '<div style="font-weight:700; margin:6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🏬 送到取货点</div>'
                ),
                unsafe_allow_html=True,
            )
            air_is_df = isinstance(air_logistics, pd.DataFrame)
            air_empty = getattr(air_logistics, "empty", True)
            air_cols = list(getattr(air_logistics, "columns", []))
            if (
                air_is_df
                and (not air_empty)
                and ("delivery_method" in air_cols)
            ):
                air_pickup = air_logistics.loc[
                    air_logistics["delivery_method"] == "pickup_point"
                ].copy()
            else:
                air_pickup = pd.DataFrame()
            if not air_pickup.empty:
                res_ap = calculate_pricing(
                    product,
                    pd.DataFrame(),
                    air_pickup,
                    "速度优先",
                )
                best = res_ap.get("best_air") or {}
                cost = res_ap.get("air_cost")
                price = res_ap.get("air_price") or 0
                stats = res_ap.get("air_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                html = _render_pricing_card(
                    grad_start="#fff3e0",
                    grad_end="#ffe0b2",
                    border_color="#ff9800",
                    shadow_rgba="rgba(255,152,0,0.15)",
                    best_name=format_logistics_name(best.get("name", ""), best.get("delivery_method", "unknown"), include_delivery=True),
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送到取货点空运方案（速度优先）")

            st.markdown(
                (
                    '<div style="font-weight:700; margin:12px 0 6px 0; '
                    'font-size:1.2em; color:#2c3e50;">🚪 送货上门</div>'
                ),
                unsafe_allow_html=True,
            )
            air_is_df = isinstance(air_logistics, pd.DataFrame)
            air_empty = getattr(air_logistics, "empty", True)
            air_cols = list(getattr(air_logistics, "columns", []))
            if (
                air_is_df
                and (not air_empty)
                and ("delivery_method" in air_cols)
            ):
                air_home = air_logistics.loc[
                    air_logistics["delivery_method"] == "home_delivery"
                ].copy()
            else:
                air_home = pd.DataFrame()
            if not air_home.empty:
                res_ah = calculate_pricing(
                    product,
                    pd.DataFrame(),
                    air_home,
                    "速度优先",
                )
                best = res_ah.get("best_air") or {}
                cost = res_ah.get("air_cost")
                price = res_ah.get("air_price") or 0
                stats = res_ah.get("air_stats") or {}
                avg_cost = stats.get("avg_cost", 0) or 0
                cost_saving = stats.get("cost_saving", 0) or 0
                avg_time = stats.get("avg_time", 0) or 0
                time_saving = stats.get("time_saving", 0) or 0
                profit_margin = product.get("target_profit_margin", 0) * 100

                total_cost = (
                    float(product.get("unit_price", 0))
                    + float(product.get("labeling_fee", 0))
                    + float(product.get("shipping_fee", 0))
                    + (cost or 0)
                    + 15 * current_rate
                )
                expected_profit = (
                    total_cost
                    * product.get("target_profit_margin", 0.2)
                    / (1 - product.get("target_profit_margin", 0.2))
                )

                time_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else (f"{best.get('min_days', 0)}-"
                          f"{best.get('max_days', 0)}天")
                )
                time_saving_display = (
                    "该物流未填写时效"
                    if best
                    and best.get("min_days", 0) == 0
                    and best.get("max_days", 0) == 0
                    else f"{time_saving:+.1f}天"
                )
                cost_display = (
                    f"¥{cost:.2f}" if cost is not None else "无法计算"
                )

                html = _render_pricing_card(
                    grad_start="#f3e5f5",
                    grad_end="#e1bee7",
                    border_color="#9c27b0",
                    shadow_rgba="rgba(156,39,176,0.15)",
                    best_name=format_logistics_name(best.get("name", ""), best.get("delivery_method", "unknown"), include_delivery=True),
                    cost_display=cost_display,
                    time_display=time_display,
                    price=price,
                    expected_profit=expected_profit,
                    profit_margin=profit_margin,
                    avg_cost=avg_cost,
                    cost_saving=cost_saving,
                    avg_time=avg_time,
                    time_saving_display=time_saving_display,
                )
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("暂无送货上门空运方案（速度优先）")

        # 已在各卡片中展示统计要点，此处移除外层统计块

        # 物流淘汰原因
        if pricing_result["all_costs_debug"]:
            st.markdown(
                (
                    '<h3 style="color: #667eea; margin-bottom: 15px;">'
                    "🔍 物流淘汰原因</h3>"
                ),
                unsafe_allow_html=True,
            )

            # 统计淘汰原因
            elimination_reasons = {}
            total_logistics = len(pricing_result["all_costs_debug"])
            eliminated_count = 0

            for debug_info in pricing_result["all_costs_debug"]:
                logistic_name = debug_info["logistic"]["name"]
                cost = debug_info["cost"]
                debug_list = debug_info["debug"]

                if cost is None:
                    eliminated_count += 1
                    # 找到淘汰原因
                    reason = None
                    for debug_line in debug_list:
                        if "返回 None" in debug_line:
                            reason = debug_line.replace(
                                "返回 None", ""
                            ).strip()
                            break
                        elif "跳过" in debug_line:
                            # 对于价格限制淘汰的情况
                            reason = debug_line.strip()
                            break

                    if reason:
                        if reason not in elimination_reasons:
                            elimination_reasons[reason] = []
                        elimination_reasons[reason].append(logistic_name)
                    else:
                        # 如果没有找到明确的原因，使用最后一个调试信息
                        if debug_list:
                            reason = debug_list[-1].strip()
                            if reason not in elimination_reasons:
                                elimination_reasons[reason] = []
                            elimination_reasons[reason].append(logistic_name)

            # 显示统计信息
            st.write(f"**总计物流规则：{total_logistics} 个**")
            st.write(f"**被淘汰物流：{eliminated_count} 个**")
            st.write(f"**可用物流：{total_logistics - eliminated_count} 个**")

            # 显示淘汰原因详情
            if elimination_reasons:
                st.markdown("**淘汰原因统计：**")
                for reason, logistics in elimination_reasons.items():
                    html_content = (
                        f"<div style='margin: 10px 0; padding: 10px; "
                        f"background: rgba(255, 193, 7, 0.1); "
                        f"border-left: 4px solid #ffc107; "
                        f"border-radius: 4px;'>"
                        f"<strong>原因：</strong>{reason}<br>"
                        f"<strong>影响物流：</strong>{len(logistics)} 个<br>"
                        f"<strong>物流名称：</strong>"
                        f"{', '.join(logistics)}</div>"
                    )
                    st.markdown(html_content, unsafe_allow_html=True)

            # 展开详细调试信息
            with st.expander("📋 查看详细调试信息"):
                for debug_info in pricing_result["all_costs_debug"]:
                    logistic_name = debug_info["logistic"]["name"]
                    cost = debug_info["cost"]
                    debug_list = debug_info["debug"]

                    status = "✅ 可用" if cost is not None else "❌ 被淘汰"
                    cost_display = (
                        f"¥{cost:.2f}" if cost is not None else "无法计算"
                    )

                    st.markdown(
                        f"**{logistic_name}** - {status} - 运费：{cost_display}"
                    )

                    if debug_list:
                        for debug_line in debug_list:
                            st.text(f"  {debug_line}")

                    st.markdown("---")

    # 确保数据库连接被关闭
    if "conn" in locals():
        _close_conn_if_sqlite(conn)


def _close_conn_if_sqlite(candidate):
    try:
        if isinstance(candidate, sqlite3.Connection):
            candidate.close()
    except sqlite3.Error:
        pass
