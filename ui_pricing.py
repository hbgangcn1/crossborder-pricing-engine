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

    with st.expander("定价明细分析"):
        cost_data = pd.DataFrame(
            {
                "项目": [
                    "产品单价",
                    "发货方运费",
                    "代贴单费用",
                    "陆运运费",
                    "空运运费",
                ],
                "金额(元)": [
                    product_dict["unit_price"],
                    product_dict["shipping_fee"],
                    product_dict["labeling_fee"],
                    land_cost if land_cost is not None else 0,
                    air_cost if air_cost is not None else 0,
                ],
            }
        )
        st.dataframe(cost_data)

        fee_data = pd.DataFrame(
            {
                "费用类型": ["活动折扣", "推广费用", "佣金", "提现费", "支付手续费"],
                "费率": [
                    f"{product_dict['promotion_discount'] * 100:.1f}%",
                    f"{product_dict['promotion_cost_rate'] * 100:.1f}%",
                    f"{product_dict['commission_rate'] * 100:.1f}%",
                    f"{product_dict['withdrawal_fee_rate'] * 100:.1f}%",
                    f"{product_dict['payment_processing_fee'] * 100:.1f}%",
                ],
            }
        )
        st.dataframe(fee_data)

        profit_rows = []
        for name, price, cost in (
            ("陆运", land_price, land_cost),
            ("空运", air_price, air_cost),
        ):
            if price is not None and cost is not None:
                total = (
                    product_dict["unit_price"]
                    + cost
                    + product_dict["shipping_fee"]
                    + product_dict["labeling_fee"]
                )
                margin = (price - total) / price
                profit_rows.append(
                    {
                        "物流类型": name,
                        "总成本(元)": total,
                        "销售价格(元)": price,
                        "利润(元)": price - total,
                        "利润率": f"{margin * 100:.2f}%",
                    }
                )
                min_margin = product_dict.get('min_profit_margin', 0.3) * 100
                if margin < product_dict.get("min_profit_margin", 0.3):
                    st.warning(
                        f"⚠️ {name}利润率低于 {min_margin:.1f}%"
                    )

        if profit_rows:
            st.dataframe(pd.DataFrame(profit_rows))
        else:
            st.info("暂无可用定价结果")

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

    # 展示所有物流的运费和详细计算过程
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

    # 展示最终定价的详细计算过程
    with st.expander("最终定价计算过程（调试）"):
        if land_name and land_debug:
            st.write(f"陆运【{land_name}】定价过程：")
            for line in land_debug:
                st.write(line)
        if air_name and air_debug:
            st.write(f"空运【{air_name}】定价过程：")
            for line in air_debug:
                st.write(line)
