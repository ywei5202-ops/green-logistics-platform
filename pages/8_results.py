"""优化结果页面 - 展示优化结果"""
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="优化结果", page_icon="📋")

st.title("📋 Step 8：优化结果")
st.markdown("查看物流网络优化详细结果")

# ===================== 检查是否有结果 =====================
results = st.session_state.get("results")

if not results:
    st.warning("⚠️ 暂无优化结果")
    st.info("""
    **请先在 Step 7「路径优化」页面运行优化计算**

    1. 🏭 仓库设置 - 设置总仓库地址和坐标
    2. 🏟️ 场馆录入 - 录入场馆信息
    3. 📦 物资需求 - 录入各场馆物资需求量
    4. 🚛 车辆配置 - 配置配送车辆类型和数量
    5. 🗺️ **Step 7 路径优化** - 运行优化计算
    6. 📋 **Step 8 优化结果** - 查看结果（本页面）
    """)
    st.stop()

# ===================== 结果概览 =====================
st.markdown("### 📊 优化结果概览")

vrp_result = results.get("vrp_result", {})
total_distance = results.get("total_distance_km", 0)
total_carbon = results.get("total_carbon_kg", 0)
baseline_carbon = results.get("baseline_carbon_kg", 0)
carbon_reduction = results.get("carbon_reduction_kg", 0)
reduction_pct = results.get("reduction_pct", 0)
num_vehicles = results.get("num_vehicles_used", 0)
optimization_method = results.get("optimization_method", "未知")
distance_method = results.get("distance_method", "未知")
clustering_method = results.get("clustering_method", "未知")

# 车辆类型名称映射
vehicle_name_map = {
    "diesel_heavy": "柴油重卡",
    "lng": "LNG天然气",
    "hev": "柴电混动",
    "phev": "插电混动",
    "bev": "纯电动",
    "fcev": "氢燃料电池"
}
vehicle_type = results.get("vehicle_type", "diesel_heavy")
vehicle_name = vehicle_name_map.get(vehicle_type, vehicle_type)

col_o1, col_o2, col_o3, col_o4 = st.columns(4)
with col_o1:
    st.metric("总行驶距离", f"{total_distance:.2f} km")
with col_o2:
    st.metric("总碳排放", f"{total_carbon:.2f} kg CO₂")
with col_o3:
    st.metric("使用车辆数", num_vehicles)
with col_o4:
    efficiency = total_carbon / max(total_distance, 0.01)
    st.metric("碳效率", f"{efficiency:.4f} kg/km")

# 优化效果高亮
if carbon_reduction > 0:
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #27ae60, #2ecc71);
                padding: 20px; border-radius: 10px; text-align: center; color: white; margin: 10px 0;">
        <h3>🌿 优化效果</h3>
        <p>相比基线（柴油车）减少碳排放 <strong style="font-size: 24px;">{carbon_reduction:.1f} kg CO₂</strong>
        ({reduction_pct:.1f}%)</p>
        <p>相当于种植 <strong style="font-size: 20px;">{carbon_reduction / 21.7:.1f} 棵</strong> 树木一年吸收量</p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #f39c12, #e67e22);
                padding: 20px; border-radius: 10px; text-align: center; color: white; margin: 10px 0;">
        <h3>⚠️ 优化效果</h3>
        <p>当前方案碳排放略高于基线，请尝试调整车辆配置</p>
    </div>
    """, unsafe_allow_html=True)

# 方法说明
method_col1, method_col2, method_col3 = st.columns(3)
with method_col1:
    st.caption(f"📏 距离计算: {distance_method}")
with method_col2:
    st.caption(f"🏭 中转仓选址: {clustering_method}")
with method_col3:
    st.caption(f"🚚 路径优化: {optimization_method}")

st.markdown("---")

# ===================== Tab展示 =====================
tab1, tab2, tab3 = st.tabs(["🗺️ 物流网络地图", "📊 碳排放对比", "📋 调度详情"])

# ======== Tab 1: 物流网络地图 ========
with tab1:
    st.subheader("🗺️ 物流网络地图")

    nodes = results.get("nodes", [])
    routes = results.get("routes", [])
    route_details = results.get("route_details", [])

    if nodes:
        center_lat = sum(n["lat"] for n in nodes) / len(nodes)
        center_lng = sum(n["lng"] for n in nodes) / len(nodes)

        m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="cartodbpositron")

        # 路线颜色
        route_colors = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue", "pink"]

        # 绘制路线
        for i, route in enumerate(routes):
            color = route_colors[i % len(route_colors)]
            coords = []
            for idx in route:
                if idx < len(nodes):
                    node = nodes[idx]
                    coords.append([node["lat"], node["lng"]])

            if len(coords) >= 2:
                route_detail = route_details[i] if i < len(route_details) else {}
                folium.PolyLine(
                    locations=coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=f"路线 {i+1}: {route_detail.get('total_distance_km', 0):.2f}km"
                ).add_to(m)

        # 绘制节点
        for i, node in enumerate(nodes):
            if node.get("is_warehouse"):
                # 仓库 - 红色星形
                folium.Marker(
                    [node["lat"], node["lng"]],
                    popup=f"<b>🏭 {node['name']}</b><br>地址: {node.get('address', '')}<br>角色: 配送中心",
                    tooltip=node["name"],
                    icon=folium.Icon(color="red", icon="star")
                ).add_to(m)
            else:
                # 场馆 - 蓝色圆点
                folium.CircleMarker(
                    [node["lat"], node["lng"]],
                    radius=10,
                    popup=f"<b>🏟️ {node['name']}</b><br>地址: {node.get('address', '')}<br>需求: {node.get('demand', 0):.0f} kg",
                    tooltip=f"{node['name']} ({node.get('demand', 0):.0f} kg)",
                    color="blue",
                    fill=True,
                    fillColor="blue",
                    fillOpacity=0.7
                ).add_to(m)

        # 图例
        legend_html = '''
        <div style="position:fixed; bottom:50px; left:50px; z-index:1000;
                    background:white; padding:10px; border-radius:5px; border:1px solid gray;">
            <h4 style="margin:0 0 5px 0;">📍 图例</h4>
            <p style="margin:3px 0;"><span style="color:red;">⭐</span> 总仓库（配送起点）</p>
            <p style="margin:3px 0;"><span style="color:blue;">●</span> 场馆（配送终点）</p>
            <p style="margin:3px 0;">— 配送路线</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width="100%", height=500)
    else:
        st.info("无节点数据")

# ======== Tab 2: 碳排放对比 ========
with tab2:
    st.subheader("📊 碳排放对比分析")

    # 基线 vs 优化方案对比
    comparison_data = pd.DataFrame({
        "方案": ["基线（柴油车）", f"优化方案（{vehicle_name}）"],
        "碳排放_kg": [baseline_carbon, total_carbon]
    })

    fig_bar = px.bar(
        comparison_data,
        x="方案",
        y="碳排放_kg",
        color="方案",
        title="碳排放对比",
        text_auto=True
    )
    fig_bar.update_layout(yaxis_title="碳排放 (kg CO₂)")
    st.plotly_chart(fig_bar, width="stretch")

    # 减排贡献
    if carbon_reduction > 0:
        reduction_data = pd.DataFrame({
            "指标": ["碳减排量", "剩余排放"],
            "数值_kg": [carbon_reduction, total_carbon]
        })

        fig_pie = px.pie(
            reduction_data,
            values="数值_kg",
            names="指标",
            title="碳排放构成",
            hole=0.4
        )
        st.plotly_chart(fig_pie, width="stretch")

    # 各路线碳排放
    if route_details:
        st.markdown("#### 各路线碳排放详情")

        route_carbon_data = []
        for i, detail in enumerate(route_details):
            route_carbon_data.append({
                "车辆": f"车辆 {i+1}",
                "距离_km": detail.get("total_distance_km", 0),
                "碳排放_kg": detail.get("total_carbon_kg", 0),
                "碳效率": detail.get("total_carbon_kg", 0) / max(detail.get("total_distance_km", 1), 0.01)
            })

        df_route_carbon = pd.DataFrame(route_carbon_data)

        fig_route = px.bar(
            df_route_carbon,
            x="车辆",
            y="碳排放_kg",
            color="距离_km",
            title="各路线碳排放分布",
            text_auto=True
        )
        st.plotly_chart(fig_route, width="stretch")

        st.dataframe(df_route_carbon, hide_index=True, width="stretch")

# ======== Tab 3: 调度详情 ========
with tab3:
    st.subheader("📋 调度详情")

    nodes = results.get("nodes", [])
    routes = results.get("routes", [])
    route_details = results.get("route_details", [])

    if routes and nodes:
        # 构建路线详情表
        dispatch_data = []

        for i, route in enumerate(routes):
            route_detail = route_details[i] if i < len(route_details) else {}

            # 获取路线节点名称
            route_names = []
            for idx in route:
                if idx < len(nodes):
                    route_names.append(nodes[idx]["name"])
                else:
                    route_names.append(f"未知点{idx}")

            # 获取路段信息
            segments = route_detail.get("segments", [])

            dispatch_data.append({
                "车辆编号": f"车辆 {i+1}",
                "车型": vehicle_name,
                "访问顺序": " → ".join(route_names),
                "站点数": len(route) - 2,
                "行驶距离_km": f"{route_detail.get('total_distance_km', 0):.2f}",
                "碳排放_kg": f"{route_detail.get('total_carbon_kg', 0):.2f}"
            })

        df_dispatch = pd.DataFrame(dispatch_data)
        st.dataframe(df_dispatch, hide_index=True, width="stretch")

        # CSV导出
        csv_data = []
        for i, route in enumerate(routes):
            route_detail = route_details[i] if i < len(route_details) else {}
            route_names = []
            for idx in route:
                if idx < len(nodes):
                    route_names.append(nodes[idx]["name"])

            csv_data.append({
                "车辆编号": f"车辆 {i+1}",
                "车型": vehicle_name,
                "路线": " → ".join(route_names),
                "站点数": len(route) - 2,
                "行驶距离_km": route_detail.get('total_distance_km', 0),
                "碳排放_kg": route_detail.get('total_carbon_kg', 0)
            })

        df_csv = pd.DataFrame(csv_data)
        csv_string = df_csv.to_csv(index=False)

        st.download_button(
            label="📥 下载调度详情CSV",
            data=csv_string,
            file_name="dispatch_details.csv",
            mime="text/csv"
        )

        # 详细路段表
        st.markdown("#### 详细路段信息")

        segment_data = []
        for i, detail in enumerate(route_details):
            segments = detail.get("segments", [])
            for j, seg in enumerate(segments):
                from_node = nodes[seg.get("from", 0)] if seg.get("from", 0) < len(nodes) else {"name": "未知"}
                to_node = nodes[seg.get("to", 0)] if seg.get("to", 0) < len(nodes) else {"name": "未知"}

                segment_data.append({
                    "车辆": f"车辆 {i+1}",
                    "路段": f"{from_node.get('name', '?')} → {to_node.get('name', '?')}",
                    "距离_km": f"{seg.get('distance_km', 0):.2f}",
                    "载重_t": f"{seg.get('load_before_ton', 0):.1f}",
                    "需求_kg": f"{seg.get('demand_kg', 0):.0f}",
                    "碳排放_kg": f"{seg.get('carbon_kg', 0):.2f}"
                })

        if segment_data:
            df_segments = pd.DataFrame(segment_data)
            st.dataframe(df_segments, hide_index=True, width="stretch")

            # 路段CSV导出
            csv_segments = df_segments.to_csv(index=False)
            st.download_button(
                label="📥 下载路段详情CSV",
                data=csv_segments,
                file_name="route_segments.csv",
                mime="text/csv"
            )
    else:
        st.info("无路线数据")

st.markdown("---")
st.caption(f"💡 优化完成时间: {results.get('timestamp', '未知')}")
