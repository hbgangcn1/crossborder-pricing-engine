import streamlit as st
import pandas as pd
import time
from db_utils import get_db, current_user_id
from logic import calculate_pricing, _debug_filter_reason


def pricing_calculator_page():
    """定价计算器页面"""
    st.session_state.t0 = time.time()
    st.write("页面开始渲染", time.strftime("%H:%M:%S"))
    st.title("物流定价计算器")
    conn, c = get_db()
    uid = current_user_id()

    # ------------- 0. 筛选选项 -------------
    col1, col2 = st.columns(2)
    with col1:
        priority = st.selectbox(
            "优先级",
            ["速度优先", "低价优先"],
            help="速度优先：优先选择时效最快的物流；低价优先：优先选择价格最低的物流"
        )
    with col2:
        delivery_filter = st.radio(
            "送货方式筛选",
            ["查看全部", "只看送货上门", "只看送到取货点"],
            horizontal=True
        )

    # ------------- 1. 选择产品 -------------
    products = pd.read_sql(
        "SELECT id, name FROM products WHERE user_id = ?", conn, params=(uid,)
    )
    if products.empty:
        st.warning("请先添加产品")
        return

    product_id = st.selectbox(
        "选择产品",
        products["id"],
        format_func=lambda x: (
            f"{x} - "
            f"{products.loc[products['id'] == x, 'name'].values[0]}"
        ),
        key="pricing_product_select",
    )

    # ------------- 2. 缓存 key -------------
    cache_key = f"pricing_cache_{uid}_{product_id}"
    ts_key = f"{cache_key}_ts"

    # ------------- 3. 直接查询 + 计算 -------------
    product = c.execute(
        "SELECT * FROM products WHERE id = ? AND user_id = ?",
        (product_id, uid)).fetchone()
    if not product:
        st.error("产品不存在")
        return
    product_dict = dict(product)

    # 构建查询条件
    delivery_conditions = []
    if delivery_filter == "只看送货上门":
        delivery_conditions.append("delivery_method = 'home_delivery'")
    elif delivery_filter == "只看送到取货点":
        delivery_conditions.append("delivery_method = 'pickup_point'")

    delivery_where = ""
    if delivery_conditions:
        delivery_where = " AND " + " AND ".join(delivery_conditions)

    land_logistics = pd.read_sql(
        f"SELECT * FROM logistics WHERE type='land' AND user_id = ?"
        f"{delivery_where}",
        conn,
        params=(uid,)).to_dict(orient="records")
    air_logistics = pd.read_sql(
        f"SELECT * FROM logistics WHERE type='air' AND user_id = ?"
        f"{delivery_where}",
        conn,
        params=(uid,)).to_dict(orient="records")

    (
        land_price,
        air_price,
        land_cost,
        air_cost,
        land_name,
        air_name,
        all_costs_debug,
        land_debug,
        air_debug,
    ) = calculate_pricing(
        product_dict,
        land_logistics,
        air_logistics,
        priority=priority
    )

    # 写入缓存
    st.session_state[cache_key] = (
        product_dict,
        land_logistics,
        air_logistics,
        land_price,
        air_price,
        land_cost,
        air_cost,
        land_name,
        air_name,
    )
    st.session_state[ts_key] = time.time()

    # ------------- 5. 后续逻辑保持不变 -------------

    # ---- 展示结果 ----
    col1, col2 = st.columns(2)
    with col1:
        if land_price is not None:
            st.markdown(
                """
                <div
                    style="
                        font-size:24px;
                        font-weight:bold;
                        margin-bottom:8px;
                    "
                >
                    最佳陆运：<span style="color:#007acc;">{land_name}</span>
                </div>
                <div style="font-size:22px; margin-bottom:4px;">
                    物流运费：<span style="color:#d9534f;">¥{land_cost:.2f}</span>
                </div>
                <div style="font-size:22px;">
                    产品定价：<span style="color:#28a745;">¥{land_price:.2f}</span>
                </div>
                """.format(
                    land_name=land_name,
                    land_cost=land_cost,
                    land_price=land_price,
                ),
                unsafe_allow_html=True,
            )
        else:
            st.info("无可用陆运")

    with col2:
        if air_price is not None:
            st.markdown(
                f"""
                <div
                    style="
                        font-size:24px;
                        font-weight:bold;
                        margin-bottom:8px;
                    "
                >
                    最佳空运：<span style="color:#007acc;">{air_name}</span>
                </div>
                <div
                    style="
                        font-size:22px;
                        margin-bottom:4px;
                    "
                >
                    物流运费：<span style="color:#d9534f;">¥{air_cost:.2f}</span>
                </div>
                <div style="font-size:22px;">
                    产品定价：<span style="color:#28a745;">¥{air_price:.2f}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("无可用空运")

    # ---- 计算平均运费和时效 ----
    # 从all_costs_debug中筛选出真正可用的物流（通过所有检查的物流）
    available_land_costs = []
    available_land_times = []
    available_air_costs = []
    available_air_times = []
    
    # 从all_costs_debug中筛选出真正可用的物流
    for item in all_costs_debug:
        log = item["logistic"]
        cost = item["cost"]
        debug_info = item["debug"]
        
        # 检查是否真正可用（通过所有检查，没有被淘汰）
        if cost is not None:
            # 检查是否因为任何原因被淘汰
            is_eliminated = any(
                "不满足重量限制" in line or 
                "超价格上限" in line or 
                "低于价格下限" in line or
                "超尺寸限制" in line or
                "不满足尺寸限制" in line or
                "返回 None" in line or
                "跳过" in line
                for line in debug_info
            )
            
            if not is_eliminated:
                min_days = log.get("min_days", 0)
                max_days = log.get("max_days", 0)
                avg_time = (min_days + max_days) / 2 if max_days > 0 else min_days
                
                if log.get("type") == "land":
                    available_land_costs.append(cost)
                    available_land_times.append(avg_time)
                elif log.get("type") == "air":
                    available_air_costs.append(cost)
                    available_air_times.append(avg_time)

    # 显示平均运费和时效信息
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        if available_land_costs:
            avg_land_cost = (sum(available_land_costs) /
                             len(available_land_costs))
            avg_land_time = (sum(available_land_times) /
                             len(available_land_times))

            if land_cost is not None:
                cost_saving = ((avg_land_cost - land_cost) /
                               avg_land_cost) * 100

                # 计算最佳陆运的时效
                best_land_time = 0
                best_land_min_days = 0
                best_land_max_days = 0
                for item in all_costs_debug:
                    log = item["logistic"]
                    if (log.get("name") == land_name and
                            log.get("type") == "land"):
                        best_land_min_days = log.get("min_days", 0)
                        best_land_max_days = log.get("max_days", 0)
                        best_land_time = ((best_land_min_days +
                                           best_land_max_days) / 2
                                          if best_land_max_days > 0
                                          else best_land_min_days)
                        break

                # 检查是否有时效数据
                if best_land_min_days == 0 and best_land_max_days == 0:
                    time_saving_text = "该物流未填写时效"
                else:
                    time_saving = avg_land_time - best_land_time
                    time_saving_text = f"{time_saving:.1f}天"

                # 根据优先级类型调整显示标签
                if priority == "速度优先":
                    cost_label = "运费差异"
                    cost_color = "#d9534f" if cost_saving < 0 else "#28a745"
                    time_label = "时效节省"
                    time_color = "#28a745"
                else:  # 低价优先
                    cost_label = "运费节省"
                    cost_color = "#28a745"
                    time_label = "时效差异"
                    # 确保time_saving已定义
                    if 'time_saving' in locals():
                        time_color = "#d9534f" if time_saving < 0 else "#28a745"
                    else:
                        time_color = "#28a745"
                
                st.markdown(
                    f"""
                    <div style="font-size:18px; margin-bottom:8px;">
                        <strong>陆运统计：</strong>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        平均运费：<span style="color:#d9534f;">
                        ¥{avg_land_cost:.2f}</span>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        {cost_label}：<span style="color:{cost_color};">
                        {cost_saving:.1f}%</span>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        平均时效：<span style="color:#007acc;">
                        {avg_land_time:.1f}天</span>
                    </div>
                    <div style="font-size:16px;">
                        {time_label}：<span style="color:{time_color};">
                        {time_saving_text}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div style="font-size:18px; margin-bottom:8px;">
                        <strong>陆运统计：</strong>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        平均运费：<span style="color:#d9534f;">
                        ¥{avg_land_cost:.2f}</span>
                    </div>
                    <div style="font-size:16px;">
                        平均时效：<span style="color:#007acc;">
                        {avg_land_time:.1f}天</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("无可用陆运数据")

    with col2:
        if available_air_costs:
            avg_air_cost = (sum(available_air_costs) /
                            len(available_air_costs))
            avg_air_time = (sum(available_air_times) /
                            len(available_air_times))

            if air_cost is not None:
                cost_saving = ((avg_air_cost - air_cost) /
                               avg_air_cost) * 100

                # 计算最佳空运的时效
                best_air_time = 0
                best_air_min_days = 0
                best_air_max_days = 0
                for item in all_costs_debug:
                    log = item["logistic"]
                    if (log.get("name") == air_name and
                            log.get("type") == "air"):
                        best_air_min_days = log.get("min_days", 0)
                        best_air_max_days = log.get("max_days", 0)
                        best_air_time = ((best_air_min_days +
                                          best_air_max_days) / 2
                                         if best_air_max_days > 0
                                         else best_air_min_days)
                        break

                # 检查是否有时效数据
                if best_air_min_days == 0 and best_air_max_days == 0:
                    time_saving_text = "该物流未填写时效"
                else:
                    time_saving = avg_air_time - best_air_time
                    time_saving_text = f"{time_saving:.1f}天"

                # 根据优先级类型调整显示标签
                if priority == "速度优先":
                    cost_label = "运费差异"
                    cost_color = "#d9534f" if cost_saving < 0 else "#28a745"
                    time_label = "时效节省"
                    time_color = "#28a745"
                else:  # 低价优先
                    cost_label = "运费节省"
                    cost_color = "#28a745"
                    time_label = "时效差异"
                    # 确保time_saving已定义
                    if 'time_saving' in locals():
                        time_color = "#d9534f" if time_saving < 0 else "#28a745"
                    else:
                        time_color = "#28a745"
                
                st.markdown(
                    f"""
                    <div style="font-size:18px; margin-bottom:8px;">
                        <strong>空运统计：</strong>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        平均运费：<span style="color:#d9534f;">
                        ¥{avg_air_cost:.2f}</span>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        {cost_label}：<span style="color:{cost_color};">
                        {cost_saving:.1f}%</span>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        平均时效：<span style="color:#007acc;">
                        {avg_air_time:.1f}天</span>
                    </div>
                    <div style="font-size:16px;">
                        {time_label}：<span style="color:{time_color};">
                        {time_saving_text}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div style="font-size:18px; margin-bottom:8px;">
                        <strong>空运统计：</strong>
                    </div>
                    <div style="font-size:16px; margin-bottom:4px;">
                        平均运费：<span style="color:#d9534f;">
                        ¥{avg_air_cost:.2f}</span>
                    </div>
                    <div style="font-size:16px;">
                        平均时效：<span style="color:#007acc;">
                        {avg_air_time:.1f}天</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("无可用空运数据")

    # 物流淘汰原因
    with st.expander("物流淘汰原因"):
        for log in land_logistics + air_logistics:
            if log is not None:
                reason = _debug_filter_reason(log, product_dict)
                if reason:
                    st.write(
                        f"❌ {log.get('name', '未知')}（{log.get('type', '未知')}）"
                        f"被淘汰：{reason}"
                    )
                else:
                    st.write(
                        f"✅ {log.get('name', '未知')}（{log.get('type', '未知')}）"
                        f"可用"
                    )

    # 展示所有物流的运费和详细计算过程（仅管理员可见）
    if st.session_state.user["role"] == "admin":
        with st.expander("所有物流运费及计算过程（调试）"):
            for item in all_costs_debug:
                log = item["logistic"]
                if log is not None:
                    st.write(
                        f"物流：{log.get('name', '未知')}（{log.get('type', '未知')}），"
                        f"运费：{item['cost']}"
                    )
                    for line in item["debug"]:
                        st.write(line)
                    st.markdown("---")
