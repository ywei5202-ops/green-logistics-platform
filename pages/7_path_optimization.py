"""路径优化页面 - 执行优化计算"""
import streamlit as st
import pandas as pd
import math
from datetime import datetime

st.set_page_config(page_title="路径优化", page_icon="🗺️")

st.title("🗺️ Step 7：路径优化")
st.markdown("执行物流网络优化计算")

# ===================== 工具函数 =====================

def haversine_distance(coord1, coord2):
    """计算两点间Haversine距离（公里）"""
    R = 6371.0
    lat1, lon1 = math.radians(coord1[1]), math.radians(coord1[0])
    lat2, lon2 = math.radians(coord2[1]), math.radians(coord2[0])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def build_distance_matrix_haversine(coords):
    """使用Haversine公式构建距离矩阵"""
    n = len(coords)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = haversine_distance(coords[i], coords[j]) * 1.3  # 道路系数
    return matrix


def greedy_vrp(distance_matrix, demands, vehicle_capacity):
    """贪心算法（最近邻）作为OR-Tools的fallback"""
    n = len(distance_matrix)
    remaining = demands.copy()
    routes = []
    remaining[0] = 0

    while sum(remaining) > 0:
        route = [0]
        current_load = 0
        current_pos = 0

        while True:
            min_dist = float('inf')
            next_node = -1

            for j in range(1, n):
                if remaining[j] > 0 and distance_matrix[current_pos][j] < min_dist:
                    min_dist = distance_matrix[current_pos][j]
                    next_node = j

            if next_node == -1:
                break

            if current_load + remaining[next_node] <= vehicle_capacity:
                route.append(next_node)
                current_load += remaining[next_node]
                remaining[next_node] = 0
                current_pos = next_node
            else:
                break

        route.append(0)
        if len(route) > 2:
            routes.append(route)

    return routes


def calc_route_carbon_greedy(route, distance_matrix, demands, vehicle_capacity, vehicle_type, emission_factor):
    """计算贪心算法的路线碳排放"""
    segments = []
    total_distance = 0.0
    total_carbon = 0.0
    current_load_ton = vehicle_capacity / 1000

    for i in range(len(route) - 1):
        from_node = route[i]
        to_node = route[i + 1]
        distance = distance_matrix[from_node][to_node]

        carbon = distance * emission_factor * current_load_ton

        segments.append({
            "from": from_node,
            "to": to_node,
            "distance_km": distance,
            "load_before_ton": current_load_ton,
            "demand_kg": demands[to_node],
            "load_after_ton": current_load_ton - demands[to_node] / 1000,
            "carbon_kg": carbon
        })

        total_distance += distance
        total_carbon += carbon
        current_load_ton -= demands[to_node] / 1000

    return {
        "route": route,
        "segments": segments,
        "total_distance_km": total_distance,
        "total_carbon_kg": total_carbon
    }


# ===================== 数据检查 =====================

def check_required_data():
    """检查必要数据是否完整"""
    warehouse = st.session_state.get("warehouse", {})
    venues = st.session_state.get("venues", [])
    demands = st.session_state.get("demands", {})
    vehicles = st.session_state.get("vehicles", [])

    missing = []
    step_map = {
        "仓库坐标": ("Step 1", 1),
        "场馆": ("Step 2", 2),
        "物资需求": ("Step 3", 3),
        "车辆配置": ("Step 4", 4)
    }

    if not warehouse.get("lng"):
        missing.append(("仓库坐标", "Step 1"))
    if len(venues) == 0:
        missing.append(("场馆", "Step 2"))
    if len(demands) == 0:
        missing.append(("物资需求", "Step 3"))
    if len(vehicles) == 0:
        missing.append(("车辆配置", "Step 4"))

    return missing


def build_nodes(warehouse, venues, demands):
    """构建节点列表"""
    nodes = []

    # 节点0: 仓库
    nodes.append({
        "node_id": 0,
        "name": warehouse.get("name", "总仓库"),
        "address": warehouse.get("address", ""),
        "lng": warehouse["lng"],
        "lat": warehouse["lat"],
        "demand": 0,
        "is_warehouse": True
    })

    # 后续节点: 场馆
    for i, venue in enumerate(venues):
        if venue.get("lng") and venue.get("lat"):
            venue_name = venue.get("name", f"场馆{i+1}")
            nodes.append({
                "node_id": i + 1,
                "name": venue_name,
                "address": venue.get("address", ""),
                "lng": venue["lng"],
                "lat": venue["lat"],
                "demand": demands.get(venue_name, 0),
                "is_warehouse": False
            })

    return nodes


# ===================== 主流程 =====================

# 检查必要数据
missing = check_required_data()

# 显示数据状态
st.markdown("### 📊 数据完整性检查")

col1, col2, col3, col4 = st.columns(4)
warehouse = st.session_state.get("warehouse", {})
venues = st.session_state.get("venues", [])
demands = st.session_state.get("demands", {})
vehicles = st.session_state.get("vehicles", [])

with col1:
    if warehouse.get("lng"):
        st.success(f"✅ 仓库已设置")
    else:
        st.error("❌ 仓库未设置")
with col2:
    st.success(f"✅ {len(venues)} 个场馆")
with col3:
    total_demand = sum(demands.values()) if demands else 0
    st.metric("总需求", f"{total_demand:,.0f} kg")
with col4:
    total_vehicles = sum(v.get("count", 0) for v in vehicles)
    st.metric("车辆数", f"{total_vehicles} 辆")

# 如果数据不完整，显示警告
if missing:
    st.markdown("---")
    missing_items = [f"**{item}**（请先完成{step}）" for item, step in missing]
    st.warning("⚠️ 数据不完整：" + " | ".join(missing_items))

    st.info("""
    **数据录入流程：**
    1. 🏭 **Step 1 仓库设置** - 设置总仓库地址和坐标
    2. 🏟️ **Step 2 场馆录入** - 录入场馆信息
    3. 📦 **Step 3 物资需求** - 录入各场馆物资需求量
    4. 🚛 **Step 4 车辆配置** - 配置配送车辆类型和数量
    """)
    st.stop()

# ======== 数据完整，显示摘要 ========
st.markdown("---")
st.markdown("### ✅ 数据完整，可以开始优化")

# 显示数据摘要
summary_col1, summary_col2, summary_col3 = st.columns(3)
with summary_col1:
    st.metric("场馆数量", len(venues))
with summary_col2:
    st.metric("总物资需求", f"{total_demand:,.0f} kg")
with summary_col3:
    st.metric("配置车辆", f"{total_vehicles} 辆")

# 侧边栏参数
st.sidebar.header("优化参数设置")

# API Key输入（可选）
api_key = st.sidebar.text_input(
    "高德API密钥（可选）",
    type="password",
    help="用于路径规划，不填则使用Haversine距离"
)

# 获取车辆配置
if vehicles:
    selected_vehicle = vehicles[0].get("vehicle_type", "diesel_heavy")
    emission_factor = vehicles[0].get("emission_factor", 0.060)
    load_ton = vehicles[0].get("load_ton", 15.0)
    vehicle_capacity = int(load_ton * 1000)
    num_vehicles = total_vehicles
else:
    st.sidebar.error("请先配置车辆")
    st.stop()

# 开始优化按钮
st.markdown("---")
st.markdown("### 🚀 执行优化")

if st.button("🚀 开始优化", type="primary", use_container_width=True):
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # ======== Step A: 构建节点列表 ========
        status_text.text("📍 Step A: 构建节点列表...")
        progress_bar.progress(0.05)

        nodes = build_nodes(warehouse, venues, demands)
        n = len(nodes)

        if n < 2:
            st.error("需要至少1个仓库 + 1个以上场馆")
            st.stop()

        coords = [(n["lng"], n["lat"]) for n in nodes]
        st.success(f"✅ 节点列表构建完成：{n}个节点（1个仓库 + {n-1}个场馆）")

        # ======== Step B: 计算距离矩阵 ========
        status_text.text("📏 Step B: 计算距离矩阵...")
        progress_bar.progress(0.15)

        if api_key:
            try:
                from utils.amap_api import get_driving_distance

                distance_matrix = [[0.0] * n for _ in range(n)]
                total_pairs = n * (n - 1) // 2
                completed = 0

                for i in range(n):
                    for j in range(i + 1, n):
                        result = get_driving_distance(
                            (coords[i][0], coords[i][1]),
                            (coords[j][0], coords[j][1]),
                            api_key
                        )
                        if result:
                            distance_matrix[i][j] = result[0]
                            distance_matrix[j][i] = result[0]
                        else:
                            dist = haversine_distance(coords[i], coords[j]) * 1.3
                            distance_matrix[i][j] = dist
                            distance_matrix[j][i] = dist

                        completed += 1
                        if completed % 5 == 0:
                            progress_bar.progress(0.15 + 0.25 * completed / total_pairs)
                            status_text.text(f"📏 Step B: 计算距离矩阵... ({completed}/{total_pairs})")

                st.success("✅ 距离矩阵计算完成（使用高德API）")
                distance_method = "高德API"

            except Exception as e:
                st.warning(f"高德API调用失败: {e}，使用Haversine距离")
                distance_matrix = build_distance_matrix_haversine(coords)
                st.success("✅ 距离矩阵计算完成（使用Haversine）")
                distance_method = "Haversine"
        else:
            distance_matrix = build_distance_matrix_haversine(coords)
            st.info("ℹ️ 未提供API密钥，使用Haversine距离")
            st.success("✅ 距离矩阵计算完成")
            distance_method = "Haversine"

        progress_bar.progress(0.4)

        # ======== Step C: K-Means中转仓选址 ========
        status_text.text("🏭 Step C: K-Means中转仓选址...")
        progress_bar.progress(0.4)

        venue_nodes = [n for n in nodes if not n["is_warehouse"]]

        if len(venue_nodes) <= 5:
            optimal_k = 1
            clustering_result = {
                "optimal_k": 1,
                "clusters": [{"cluster_id": 0, "centroid": None, "venues": venue_nodes}]
            }
            st.info("ℹ️ 场馆数量≤5，不设中转仓，直接从仓库配送")
            clustering_method = "无中转仓"
        else:
            try:
                from utils.clustering import select_warehouse_locations

                venue_coords = [(v["lng"], v["lat"]) for v in venue_nodes]
                venue_weights = [v["demand"] for v in venue_nodes]

                clustering_result = select_warehouse_locations(
                    venue_coords,
                    venue_weights,
                    max_warehouses=6
                )

                optimal_k = clustering_result.get("optimal_k", 1)
                st.success(f"✅ K-Means选址完成，最优中转仓数量: {optimal_k}")
                clustering_method = f"K-Means (K={optimal_k})"

            except Exception as e:
                st.warning(f"K-Means选址失败: {e}")
                optimal_k = 1
                clustering_result = {
                    "optimal_k": 1,
                    "clusters": [{"cluster_id": 0, "centroid": None, "venues": venue_nodes}]
                }
                clustering_method = "失败，使用无中转仓方案"

        # 为节点分配聚类ID
        for node in nodes:
            if not node["is_warehouse"]:
                for i, v in enumerate(venue_nodes):
                    if node["name"] == v["name"]:
                        node["cluster_id"] = clustering_result.get("labels", [0] * len(venue_nodes))[i] if "labels" in clustering_result else 0
                        break

        progress_bar.progress(0.55)

        # ======== Step D: VRP路径优化 ========
        status_text.text("🚚 Step D: VRP路径优化...")
        progress_bar.progress(0.55)

        demands_list = [n["demand"] for n in nodes]

        try:
            from utils.vrp_solver import solve_green_cvrp

            vrp_result = solve_green_cvrp(
                distance_matrix=distance_matrix,
                demands=demands_list,
                vehicle_capacity=vehicle_capacity,
                num_vehicles=num_vehicles,
                vehicle_type=selected_vehicle,
                depot=0,
                time_limit_seconds=60
            )

            if not vrp_result or not vrp_result.get("routes"):
                raise Exception("VRP求解返回空结果")

            st.success(f"✅ VRP优化完成（使用OR-Tools），使用 {vrp_result.get('num_vehicles_used', 0)} 辆车")
            optimization_method = "OR-Tools"

        except Exception as e:
            st.warning(f"OR-Tools求解失败: {e}，使用贪心算法")

            routes = greedy_vrp(distance_matrix, demands_list, vehicle_capacity)

            route_details = []
            for route in routes:
                detail = calc_route_carbon_greedy(
                    route, distance_matrix, demands_list,
                    vehicle_capacity, selected_vehicle, emission_factor
                )
                route_details.append(detail)

            total_distance = sum(d["total_distance_km"] for d in route_details)
            total_carbon = sum(d["total_carbon_kg"] for d in route_details)

            vrp_result = {
                "success": True,
                "routes": routes,
                "route_details": route_details,
                "total_distance_km": total_distance,
                "total_carbon_kg": total_carbon,
                "num_vehicles_used": len(routes),
                "vehicle_type": selected_vehicle,
                "vehicle_capacity": vehicle_capacity
            }

            st.success("✅ VRP优化完成（使用贪心算法）")
            optimization_method = "贪心算法"

        progress_bar.progress(0.75)

        # ======== Step E: 碳排放计算 ========
        status_text.text("🌿 Step E: 计算碳排放...")
        progress_bar.progress(0.75)

        # 计算基线碳排放（假设使用柴油车）
        baseline_ef = 0.080  # kg CO₂/吨·km（柴油车较高排放因子）
        baseline_carbon = sum(demands_list) / 1000 * vrp_result["total_distance_km"] * baseline_ef

        optimized_carbon = vrp_result["total_carbon_kg"]
        carbon_reduction = baseline_carbon - optimized_carbon
        reduction_pct = (carbon_reduction / baseline_carbon * 100) if baseline_carbon > 0 else 0

        st.success(f"✅ 碳排放计算完成")

        progress_bar.progress(0.9)

        # ======== 保存结果 ========
        status_text.text("💾 保存结果...")

        results = {
            "nodes": nodes,
            "routes": vrp_result.get("routes", []),
            "route_details": vrp_result.get("route_details", []),
            "distance_matrix": distance_matrix,
            "clustering_result": clustering_result,
            "vrp_result": vrp_result,
            "total_distance_km": vrp_result.get("total_distance_km", 0),
            "total_carbon_kg": vrp_result.get("total_carbon_kg", 0),
            "num_vehicles_used": vrp_result.get("num_vehicles_used", 0),
            "baseline_carbon_kg": baseline_carbon,
            "carbon_reduction_kg": carbon_reduction,
            "reduction_pct": reduction_pct,
            "optimization_method": optimization_method,
            "clustering_method": clustering_method,
            "distance_method": distance_method,
            "vehicle_type": selected_vehicle,
            "vehicle_capacity": vehicle_capacity,
            "emission_factor": emission_factor,
            "num_vehicles": num_vehicles,
            "timestamp": datetime.now().isoformat()
        }

        st.session_state["results"] = results

        progress_bar.progress(1.0)
        status_text.text("✅ 完成！")

        st.markdown("---")
        st.success("🎉 **优化完成！请前往 Step 8 查看详细结果**")

        # 显示简要结果
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            st.metric("总距离", f"{vrp_result.get('total_distance_km', 0):.2f} km")
        with col_r2:
            st.metric("总碳排放", f"{vrp_result.get('total_carbon_kg', 0):.2f} kg")
        with col_r3:
            st.metric("使用车辆", vrp_result.get('num_vehicles_used', 0))
        with col_r4:
            st.metric("减排比例", f"{reduction_pct:.1f}%")

    except Exception as e:
        st.error(f"优化过程出错: {e}")
        import traceback
        st.code(traceback.format_exc())
else:
    st.info("👆 点击上方「🚀 开始优化」按钮执行优化计算")
