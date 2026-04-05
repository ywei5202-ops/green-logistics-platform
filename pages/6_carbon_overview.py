"""碳排放概览页面"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="碳排放概览", page_icon="📊")

st.title("📊 Step 6：碳排放概览")
st.markdown("赛事物流碳足迹实时监控")

# ===================== 检查优化结果 =====================
optimization_result = st.session_state.get("optimization_result")
vrp_result = st.session_state.get("vrp_result")
vehicles = st.session_state.get("vehicles", [])
demands = st.session_state.get("demands", {})

# 优先使用optimization_result，其次vrp_result
result = optimization_result or vrp_result

# ===================== 关键指标展示 =====================
if result and isinstance(result, dict) and result.get("success") or (result and result.get("routes")):
    # 总碳排放
    total_carbon_kg = result.get("total_carbon_kg", 0)

    # 基线碳排放（假设使用柴油重卡）
    baseline_ef = 0.060  # kg CO₂/吨·km
    total_demand_ton = sum(demands.values()) / 1000 if demands else 1
    total_distance_km = result.get("total_distance_km", 100)
    baseline_carbon_kg = total_demand_ton * total_distance_km * baseline_ef

    # 减排百分比
    if baseline_carbon_kg > 0:
        reduction_pct = (baseline_carbon_kg - total_carbon_kg) / baseline_carbon_kg * 100
    else:
        reduction_pct = 0

    # 种树数量（每棵树年吸收21.7千克二氧化碳）
    tree_equivalent = total_carbon_kg / 21.7

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "总碳排放量",
            f"{total_carbon_kg:,.1f} kg CO₂",
            delta=f"-{(100 - reduction_pct):.1f}%" if reduction_pct > 0 else None
        )
    with col2:
        st.metric(
            "对比基线减排",
            f"{reduction_pct:.1f}%",
            delta="相比柴油车" if reduction_pct > 0 else "需优化"
        )
    with col3:
        st.metric(
            "相当于种树",
            f"{tree_equivalent:.0f} 棵/年",
            delta="每棵年吸21.7kg CO₂"
        )

    st.markdown("---")

    # ===================== 碳排放构成分析 =====================
    st.subheader("🥧 碳排放构成分析")

    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        # 干线运输 vs 终端配送构成
        if result.get("route_details"):
            # 按路线分类
            route_carbon = []
            for i, detail in enumerate(result.get("route_details", [])):
                route_carbon.append({
                    "路线": f"车辆 {i+1}",
                    "碳排放_kg": detail.get("total_carbon_kg", 0),
                    "距离_km": detail.get("total_distance_km", 0)
                })

            df_routes = pd.DataFrame(route_carbon)
            df_routes["类型"] = df_routes["距离_km"].apply(
                lambda x: "干线运输" if x > 30 else "终端配送"
            )

            pie_data = df_routes.groupby("类型")["碳排放_kg"].sum().reset_index()

            fig_pie1 = px.pie(
                pie_data,
                values="碳排放_kg",
                names="类型",
                title="干线运输 vs 终端配送 碳排放构成",
                hole=0.4
            )
            st.plotly_chart(fig_pie1, width="stretch")
        else:
            st.info("无可用路线数据")

    with col_pie2:
        # 车辆类型构成
        vehicle_type_in_result = result.get("vehicle_type", "diesel_heavy")
        vehicle_name_map = {
            "diesel_heavy": "柴油重卡",
            "lng": "LNG天然气",
            "hev": "柴电混动",
            "phev": "插电混动",
            "bev": "纯电动",
            "fcev": "氢燃料电池"
        }
        vehicle_name = vehicle_name_map.get(vehicle_type_in_result, vehicle_type_in_result)

        pie_data2 = pd.DataFrame({
            "类型": [vehicle_name, "其他（假设）"],
            "碳排放_kg": [total_carbon_kg * 0.7, total_carbon_kg * 0.3]
        })

        fig_pie2 = px.pie(
            pie_data2,
            values="碳排放_kg",
            names="类型",
            title="车辆类型碳排放构成",
            hole=0.4
        )
        st.plotly_chart(fig_pie2, width="stretch")

    # ===================== 碳排放趋势（使用模拟数据） =====================
    st.subheader("📈 碳排放趋势")

    if result.get("route_details"):
        route_details = result.get("route_details", [])

        trend_data = []
        for i, detail in enumerate(route_details):
            route = detail.get("route", [])
            for seg in detail.get("segments", []):
                trend_data.append({
                    "路段": f"{seg.get('from', 0)}→{seg.get('to', 0)}",
                    "碳排放_kg": seg.get("carbon_kg", 0),
                    "距离_km": seg.get("distance_km", 0),
                    "载重_t": seg.get("load_before_ton", 0)
                })

        df_trend = pd.DataFrame(trend_data)

        fig_bar = px.bar(
            df_trend,
            x="路段",
            y="碳排放_kg",
            color="载重_t",
            title="各路段碳排放分布",
            text_auto=True
        )
        st.plotly_chart(fig_bar, width="stretch")

    # ===================== 详细数据表 =====================
    st.subheader("📋 路线详情")

    if result.get("route_details"):
        detail_table = []
        for i, detail in enumerate(result.get("route_details", [])):
            detail_table.append({
                "车辆编号": f"车辆 {i+1}",
                "车型": vehicle_name_map.get(result.get("vehicle_type", ""), result.get("vehicle_type", "")),
                "行驶距离_km": f"{detail.get('total_distance_km', 0):.2f}",
                "碳排放_kg": f"{detail.get('total_carbon_kg', 0):.2f}",
                "站点数": len(detail.get("route", [])) - 2
            })

        df_detail = pd.DataFrame(detail_table)
        st.dataframe(df_detail, hide_index=True, width="stretch")
else:
    # ===================== 无数据提示 =====================
    st.warning("⚠️ 暂无优化计算结果")

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.info("""
        **请先完成以下步骤：**
        1. 🏭 仓库设置 - 设置总仓库
        2. 🏟️ 场馆录入 - 添加配送场馆
        3. 📦 物资需求 - 录入物资需求
        4. 🚛 车辆配置 - 配置配送车辆
        5. 🗺️ 路径优化 - 运行优化计算
        """)
    with col_info2:
        st.info("""
        **或在「优化结果」页面**
        点击「🚀 开始优化」按钮
        运行完整的物流网络优化流程
        """)

    st.markdown("---")

    # 即使没有优化结果，也显示车型库概览
    st.subheader("📊 车型碳排放参考")

    # 从车型库加载数据
    import json
    try:
        with open("data/vehicle_types.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            vehicle_list = data.get("vehicle_types", []) if isinstance(data, dict) else data
    except:
        vehicle_list = []

    if vehicle_list:
        ref_data = []
        for v in vehicle_list:
            ref_data.append({
                "车型": v.get("name", ""),
                "排放因子": f"{v.get('emission_factor_default', 0):.3f}",
                "减排对比": v.get("reduction_vs_diesel", "N/A")
            })

        df_ref = pd.DataFrame(ref_data)
        st.dataframe(df_ref, hide_index=True, width="stretch")

        st.caption("💡 参考：排放因子单位为 kg CO₂/吨·km，越低越环保")

st.markdown("---")
st.caption("💡 提示：种树计算基于每棵树每年吸收约21.7千克二氧化碳")
