import streamlit as st
import pandas as pd
from logic import calculate_pricing
from db_utils import get_db, current_user_id


def pricing_calculator_page():
    """定价计算器页面"""
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
    from exchange_service import ExchangeRateService

    # 初始化汇率变量
    current_rate = 0.0904  # 默认兜底汇率

    try:
        exchange_service = ExchangeRateService()
        current_rate = exchange_service.get_exchange_rate()
        st.sidebar.success(f"当前汇率: 1 CNY = {current_rate:.2f} RUB")
    except Exception as e:
        st.sidebar.warning(f"汇率获取失败: {str(e)}")
        # 使用默认汇率，current_rate已经在上面初始化了

    conn, c = get_db()
    uid = current_user_id()

    # 获取用户的产品列表
    products = pd.read_sql(
        "SELECT id, name, category FROM products WHERE user_id = ?",
        conn,
        params=(uid,),
    )

    if products.empty:
        st.warning("请先添加产品")
        return

    # 产品选择
    st.markdown(
        '<h3 style="color: #2c3e50; margin-bottom: 20px; font-size: 1.5em; '
        "font-weight: 600; border-bottom: 2px solid #3498db; "
        'padding-bottom: 8px;">📦 产品选择</h3>',
        unsafe_allow_html=True,
    )

    selected_product_name = st.selectbox(
        "选择产品", products["name"].tolist(), key="product_select"
    )

    if not selected_product_name:
        st.info("请选择一个产品")
        return

    # 获取选中产品的详细信息
    product = pd.read_sql(
        "SELECT * FROM products WHERE name = ? AND user_id = ?",
        conn,
        params=(selected_product_name, uid),
    ).iloc[0]

    # 物流筛选选项
    st.markdown(
        '<h3 style="color: #2c3e50; margin-bottom: 20px; font-size: 1.5em; '
        "font-weight: 600; border-bottom: 2px solid #3498db; "
        'padding-bottom: 8px;">🚚 物流筛选</h3>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        priority = st.selectbox(
            "优先级选择", ["低价优先", "速度优先"], key="priority_select"
        )
    with col2:
        delivery_filter = st.selectbox(
            "送货方式筛选",
            ["全部", "送货上门", "送货到取货点"],
            key="delivery_filter",
        )

    # 计算按钮
    if st.button("🚀 开始计算", key="calculate_button"):
        # 获取物流数据
        logistics_query = "SELECT * FROM logistics WHERE user_id = ?"
        logistics_df = pd.read_sql(logistics_query, conn, params=(uid,))

        if logistics_df.empty:
            st.error("请先添加物流规则")
            return

        # 应用送货方式筛选
        if delivery_filter != "全部":
            delivery_map = {
                "送货上门": "home_delivery",
                "送货到取货点": "pickup_point",
            }
            delivery_method = delivery_map[delivery_filter]
            logistics_df = logistics_df[
                logistics_df["delivery_method"] == delivery_method
            ]

        if logistics_df.empty:
            st.error(f"没有符合条件的{delivery_filter}物流规则")
            return

        # 分离陆运和空运物流
        land_logistics = logistics_df[logistics_df["type"] == "land"]
        air_logistics = logistics_df[logistics_df["type"] == "air"]

        # 计算定价
        pricing_result = calculate_pricing(
            product, land_logistics, air_logistics, priority
        )

        # 显示结果
        st.markdown(
            '<h3 style="color: #2c3e50; margin-bottom: 20px; '
            'font-size: 1.5em; font-weight: 600; '
            'border-bottom: 2px solid #3498db; '
            'padding-bottom: 8px;">📊 计算结果</h3>',
            unsafe_allow_html=True,
        )

        # 产品信息
        st.markdown(
            '<h4 style="color: #34495e; margin-bottom: 15px; '
            'font-size: 1.2em; font-weight: 600;">📦 产品信息</h4>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, "
            "#f8f9fa 0%, #e9ecef 100%); border-radius: 12px; "
            "padding: 20px; margin: 15px 0; "
            "border-left: 4px solid #28a745;">
                <div style="font-size: 1.1em; color: #2c3e50; "
                "margin-bottom: 8px;">
                    <strong>产品名称：</strong>{product['name']}
                </div>
                <div style="font-size: 1.1em; color: #2c3e50; "
                "margin-bottom: 8px;">
                    <strong>产品类别：</strong>{product['category']}
                </div>
                <div style="font-size: 1.1em; color: #2c3e50;">
                    <strong>重量：</strong>{product['weight_g']}g
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 定价结果 - 合并最佳物流方案
        st.markdown(
            '<h4 style="color: #34495e; margin-bottom: 15px; '
            'font-size: 1.2em; font-weight: 600;">💰 定价结果</h4>',
            unsafe_allow_html=True,
        )

        suggested_price = pricing_result["suggested_price"]
        if suggested_price is not None:
            col_land, col_air = st.columns(2)

            with col_land:
                if pricing_result["best_land"]:
                    best_land = pricing_result["best_land"]
                    land_cost = pricing_result["land_cost"]
                    land_cost_display = (
                        f"¥{land_cost:.2f}"
                        if land_cost is not None
                        else "无法计算"
                    )
                    # 送货方式映射
                    delivery_method_map = {
                        "pickup_point": "送到取货点",
                        "home_delivery": "送货上门",
                    }
                    delivery_method_display = (
                        delivery_method_map.get(
                            best_land.get("delivery_method"),
                            best_land.get("delivery_method", "未知"),
                        )
                    )
                    # 使用logic.py中已计算好的正确值
                    land_price = pricing_result.get('land_price', 0)
                    # 为陆运单独计算利润和利润率
                    if land_price and pricing_result.get('land_cost'):
                        land_total_cost = (
                            product['unit_price'] +
                            product['labeling_fee'] +
                            product['shipping_fee'] +
                            pricing_result.get('land_cost', 0) +
                            15 * current_rate
                        )
                        land_profit = (land_total_cost *
                                       product['target_profit_margin'] /
                                       (1 - product['target_profit_margin']))
                        land_profit_margin = (product['target_profit_margin'] *
                                              100)
                    else:
                        land_profit = 0
                        land_profit_margin = 0

                    # 构建陆运卡片HTML
                    land_card_html = (
                        f"<div style='background: linear-gradient(135deg, "
                        f"#e3f2fd 0%, #bbdefb 100%); border-radius: 12px; "
                        f"padding: 20px; margin: 10px 0; "
                        f"border-left: 4px solid #2196f3; "
                        f"box-shadow: 0 4px 12px rgba(33, 150, 243, 0.15);'>"
                        f"<div style='font-size: 1.3em; color: #1976d2; "
                        f"font-weight: 600; margin-bottom: 12px;'>"
                        f"🚛 最佳陆运</div>"
                        f"<div style='font-size: 1.4em; color: #e67e22; "
                        f"font-weight: 700; margin-bottom: 10px; "
                        f"text-shadow: 1px 1px 2px rgba(0,0,0,0.1);'>"
                        f"{best_land['name']}</div>"
                        f"<div style='font-size: 1.2em; color: #34495e; "
                        f"margin-bottom: 8px;'>"
                        f"运费：<span style='color: #e74c3c; "
                        f"font-weight: 600; font-size: 1.1em;'>"
                        f"{land_cost_display}</span></div>"
                        f"<div style='font-size: 1.2em; color: #34495e; "
                        f"margin-bottom: 8px;'>"
                        f"时效：<span style='font-weight: 600;'>"
                        f"{best_land['min_days']}-"
                        f"{best_land['max_days']}天</span></div>"
                        f"<div style='font-size: 1.2em; color: #34495e; "
                        f"margin-bottom: 8px;'>"
                        f"送货方式：<span style='font-weight: 600;'>"
                        f"{delivery_method_display}</span></div>"
                        f"<hr style='margin: 15px 0; border: none; "
                        f"border-top: 2px solid rgba(52, 73, 94, 0.2);'>"
                        f"<div style='font-size: 1.2em; color: #2c3e50; "
                        f"margin-bottom: 8px;'>"
                        f"建议售价：<span style='color: #e74c3c; "
                        f"font-weight: 700; font-size: 1.3em; "
                        f"text-shadow: 1px 1px 2px rgba(0,0,0,0.1);'>"
                        f"¥{land_price:.2f}</span></div>"
                        f"<div style='font-size: 1.2em; color: #2c3e50; "
                        f"margin-bottom: 8px;'>"
                        f"预期利润：<span style='color: #27ae60; "
                        f"font-weight: 600;'>"
                        f"¥{land_profit:.2f}</span></div>"
                        f"<div style='font-size: 1.2em; color: #2c3e50;'>"
                        f"利润率：<span style='color: #27ae60; "
                        f"font-weight: 600;'>"
                        f"{land_profit_margin:.1f}%</span></div>"
                        f"</div>"
                    )
                    st.markdown(land_card_html, unsafe_allow_html=True)
                else:
                    st.markdown(
                        """
                        <div style="background: linear-gradient(135deg, "
                        "#f5f5f5 0%, #e0e0e0 100%); border-radius: 12px; "
                        "padding: 20px; margin: 10px 0; "
                        "border-left: 4px solid #9e9e9e; text-align: center;">
                            <div style="font-size: 1.1em; color: #757575;">
                                暂无陆运方案
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            with col_air:
                if pricing_result["best_air"]:
                    best_air = pricing_result["best_air"]
                    air_cost = pricing_result["air_cost"]
                    air_cost_display = (
                        f"¥{air_cost:.2f}"
                        if air_cost is not None
                        else "无法计算"
                    )
                    # 送货方式映射
                    delivery_method_map = {
                        "pickup_point": "送到取货点",
                        "home_delivery": "送货上门",
                    }
                    delivery_method_display = (
                        delivery_method_map.get(
                            best_air.get("delivery_method"),
                            best_air.get("delivery_method", "未知"),
                        )
                    )
                    # 使用logic.py中已计算好的正确值
                    air_price = pricing_result.get('air_price', 0)
                    # 为空运单独计算利润和利润率
                    if air_price and pricing_result.get('air_cost'):
                        air_total_cost = (
                            product['unit_price'] +
                            product['labeling_fee'] +
                            product['shipping_fee'] +
                            pricing_result.get('air_cost', 0) +
                            15 * current_rate
                        )
                        air_profit = (air_total_cost *
                                      product['target_profit_margin'] /
                                      (1 - product['target_profit_margin']))
                        air_profit_margin = (product['target_profit_margin'] *
                                             100)
                    else:
                        air_profit = 0
                        air_profit_margin = 0

                    # 构建空运卡片HTML
                    air_card_html = (
                        f"<div style='background: linear-gradient(135deg, "
                        f"#fff3e0 0%, #ffe0b2 100%); border-radius: 12px; "
                        f"padding: 20px; margin: 10px 0; "
                        f"border-left: 4px solid #ff9800; "
                        f"box-shadow: 0 4px 12px rgba(255, 152, 0, 0.15);'>"
                        f"<div style='font-size: 1.3em; color: #f57c00; "
                        f"font-weight: 600; margin-bottom: 12px;'>"
                        f"✈️ 最佳空运</div>"
                        f"<div style='font-size: 1.4em; color: #8e44ad; "
                        f"font-weight: 700; margin-bottom: 10px; "
                        f"text-shadow: 1px 1px 2px rgba(0,0,0,0.1);'>"
                        f"{best_air['name']}</div>"
                        f"<div style='font-size: 1.2em; color: #34495e; "
                        f"margin-bottom: 8px;'>"
                        f"运费：<span style='color: #e74c3c; "
                        f"font-weight: 600; font-size: 1.1em;'>"
                        f"{air_cost_display}</span></div>"
                        f"<div style='font-size: 1.2em; color: #34495e; "
                        f"margin-bottom: 8px;'>"
                        f"时效：<span style='font-weight: 600;'>"
                        f"{best_air['min_days']}-"
                        f"{best_air['max_days']}天</span></div>"
                        f"<div style='font-size: 1.2em; color: #34495e; "
                        f"margin-bottom: 8px;'>"
                        f"送货方式：<span style='font-weight: 600;'>"
                        f"{delivery_method_display}</span></div>"
                        f"<hr style='margin: 15px 0; border: none; "
                        f"border-top: 2px solid rgba(52, 73, 94, 0.2);'>"
                        f"<div style='font-size: 1.2em; color: #2c3e50; "
                        f"margin-bottom: 8px;'>"
                        f"建议售价：<span style='color: #e74c3c; "
                        f"font-weight: 700; font-size: 1.3em; "
                        f"text-shadow: 1px 1px 2px rgba(0,0,0,0.1);'>"
                        f"¥{air_price:.2f}</span></div>"
                        f"<div style='font-size: 1.2em; color: #2c3e50; "
                        f"margin-bottom: 8px;'>"
                        f"预期利润：<span style='color: #27ae60; "
                        f"font-weight: 600;'>"
                        f"¥{air_profit:.2f}</span></div>"
                        f"<div style='font-size: 1.2em; color: #2c3e50;'>"
                        f"利润率：<span style='color: #27ae60; "
                        f"font-weight: 600;'>"
                        f"{air_profit_margin:.1f}%</span></div>"
                        f"</div>"
                    )
                    st.markdown(air_card_html, unsafe_allow_html=True)
                else:
                    st.markdown(
                        """
                        <div style="background: linear-gradient(135deg, "
                        "#f5f5f5 0%, #e0e0e0 100%); border-radius: 12px; "
                        "padding: 20px; margin: 10px 0; "
                        "border-left: 4px solid #9e9e9e; text-align: center;">
                            <div style="font-size: 1.1em; color: #757575;">
                                暂无空运方案
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                """
                <div style="background: linear-gradient(135deg, "
                "#ffebee 0%, #ffcdd2 100%); border-radius: 12px; "
                "padding: 20px; margin: 15px 0; "
                "border-left: 4px solid #f44336;">
                    <div style="font-size: 1.1em; color: #c62828; "
                    "text-align: center;">
                        ⚠️ 无法计算建议售价，请检查物流规则是否满足产品要求
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 统计信息
        if pricing_result["land_stats"] or pricing_result["air_stats"]:
            col_land_stats, col_air_stats = st.columns(2)

            with col_land_stats:
                if pricing_result["land_stats"]:
                    st.markdown(
                        '<h3 style="color: #667eea; margin-bottom: 15px;">'
                        '📈 陆运统计</h3>',
                        unsafe_allow_html=True,
                    )

                    land_stats = pricing_result["land_stats"]
                    avg_cost = land_stats["avg_cost"]
                    avg_cost_display = (
                        f"¥{avg_cost:.2f}" if avg_cost is not None else "无法计算"
                    )
                    st.write(f"平均运费：{avg_cost_display}")

                    # 动态显示节省运费或运费差异
                    cost_saving = land_stats["cost_saving"]
                    cost_label = "节省运费" if cost_saving >= 0 else "运费差异"
                    cost_color = "green" if cost_saving >= 0 else "red"
                    st.markdown(
                        f"<span style='color: {cost_color};'>"
                        f"{cost_label}：{cost_saving:+.1f}%</span>",
                        unsafe_allow_html=True,
                    )

                    st.write(f"平均时效：{land_stats['avg_time']:.1f}天")

                    # 动态显示时效节省或时效差异
                    time_saving = land_stats["time_saving"]
                    time_label = "时效节省" if time_saving >= 0 else "时效差异"
                    time_color = "green" if time_saving >= 0 else "red"
                    st.markdown(
                        f"<span style='color: {time_color};'>"
                        f"{time_label}：{time_saving:+.1f}天</span>",
                        unsafe_allow_html=True,
                    )

            with col_air_stats:
                if pricing_result["air_stats"]:
                    st.markdown(
                        '<h3 style="color: #667eea; margin-bottom: 15px;">'
                        '📈 空运统计</h3>',
                        unsafe_allow_html=True,
                    )

                    air_stats = pricing_result["air_stats"]
                    avg_cost = air_stats["avg_cost"]
                    avg_cost_display = (
                        f"¥{avg_cost:.2f}" if avg_cost is not None else "无法计算"
                    )
                    st.write(f"平均运费：{avg_cost_display}")

                    # 动态显示节省运费或运费差异
                    cost_saving = air_stats["cost_saving"]
                    cost_label = "节省运费" if cost_saving >= 0 else "运费差异"
                    cost_color = "green" if cost_saving >= 0 else "red"
                    st.markdown(
                        f"<span style='color: {cost_color};'>"
                        f"{cost_label}：{cost_saving:+.1f}%</span>",
                        unsafe_allow_html=True,
                    )

                    st.write(f"平均时效：{air_stats['avg_time']:.1f}天")

                    # 动态显示时效节省或时效差异
                    time_saving = air_stats["time_saving"]
                    time_label = "时效节省" if time_saving >= 0 else "时效差异"
                    time_color = "green" if time_saving >= 0 else "red"
                    st.markdown(
                        f"<span style='color: {time_color};'>"
                        f"{time_label}：{time_saving:+.1f}天</span>",
                        unsafe_allow_html=True,
                    )

        # 物流淘汰原因
        if pricing_result["all_costs_debug"]:
            st.markdown(
                '<h3 style="color: #667eea; margin-bottom: 15px;">'
                '🔍 物流淘汰原因</h3>',
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
