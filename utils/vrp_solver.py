"""Green CVRP求解器 - 目标函数为最小化总碳排放

基于Google OR-Tools实现
"""
from typing import List, Tuple, Dict, Optional
import numpy as np
import json
from pathlib import Path
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp


# 加载车型库
def load_vehicle_types():
    """从JSON文件加载车型库"""
    try:
        with open("data/vehicle_types.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "vehicle_types" in data:
                return data["vehicle_types"]
            return data
    except:
        try:
            with open("green-logistics-platform/data/vehicle_types.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "vehicle_types" in data:
                    return data["vehicle_types"]
                return data
        except:
            return []


# 车型库缓存
_vehicle_types_cache = None

def get_vehicle_params(vehicle_type_id: str) -> Dict:
    """获取车型参数"""
    global _vehicle_types_cache
    if _vehicle_types_cache is None:
        _vehicle_types_cache = {v["id"]: v for v in load_vehicle_types()}

    vehicle = _vehicle_types_cache.get(vehicle_type_id, {})
    return {
        "emission_factor": vehicle.get("emission_factor_default", 0.060),
        "max_load_ton": vehicle.get("max_load_ton_default", 15.0),
        "fuel_consumption": vehicle.get("fuel_consumption", "N/A")
    }


# 默认车辆参数
DEFAULT_PARAMS = {
    "emission_factor": 0.060,  # kg CO₂/吨·km
    "max_load_ton": 15.0,
    "fuel_consumption": "25-38 L柴油/100km"
}


def _calc_carbon_edge(
    from_node: int,
    to_node: int,
    distance_matrix: List[List[float]],
    current_load_ton: float,
    vehicle_type: str,
    vehicle_capacity: float
) -> float:
    """
    计算两个节点间行驶的碳排放（作为边权重）

    公式: carbon = distance × emission_factor × load_ton

    Args:
        from_node: 起点索引
        to_node: 终点索引
        distance_matrix: 距离矩阵
        current_load_ton: 当前载重（吨）
        vehicle_type: 车辆类型ID
        vehicle_capacity: 车辆容量（吨）

    Returns:
        碳排放量（kg CO2）
    """
    params = get_vehicle_params(vehicle_type)
    emission_factor = params["emission_factor"]  # kg CO₂/吨·km

    distance = distance_matrix[from_node][to_node]
    if distance <= 0:
        return 0.0

    # Carbon emission = distance × emission_factor × load_ton
    carbon = distance * emission_factor * current_load_ton

    return carbon


class GreenCVRP:
    """Green CVRP求解器 - 最小化碳排放"""

    def __init__(
        self,
        distance_matrix: List[List[float]],
        demands: List[float],
        vehicle_capacity: float,
        vehicle_type: str = "diesel_heavy"
    ):
        """
        初始化求解器

        Args:
            distance_matrix: N×N距离矩阵（公里）
            demands: 各节点需求量（千克），索引0为仓库（需求为0）
            vehicle_capacity: 车辆载重上限（千克）
            vehicle_type: 车辆类型ID
        """
        self.distance_matrix = distance_matrix
        self.demands = demands
        self.num_nodes = len(distance_matrix)
        self.vehicle_capacity = vehicle_capacity
        self.vehicle_type = vehicle_type

        # 创建求解器
        self.manager = None
        self.routing = None
        self.solution = None

        # 结果
        self.routes = []
        self.total_distance = 0.0
        self.total_carbon = 0.0

    def _create_model(self, num_vehicles: int, depot: int = 0):
        """创建CVRP模型"""
        self.manager = pywrapcp.RoutingIndexManager(
            self.num_nodes,
            num_vehicles,
            depot
        )

        self.routing = pywrapcp.RoutingModel(self.manager)

        # 创建碳排放回调（考虑载重变化）
        # 注意：OR-Tools的arc cost是静态的，我们用平均载重估算
        params = get_vehicle_params(self.vehicle_type)
        emission_factor = params["emission_factor"]  # kg CO₂/吨·km

        def carbon_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            distance = self.distance_matrix[from_node][to_node]

            # 使用平均载重（约为容量的一半）作为估算
            avg_load_ton = self.vehicle_capacity * 0.5 / 1000  # 转换为吨
            carbon = distance * emission_factor * avg_load_ton

            return int(carbon * 1000)  # 转换为毫克作为整数

        carbon_callback_index = self.routing.RegisterTransitCallback(carbon_callback)
        self.routing.SetArcCostEvaluatorOfAllVehicles(carbon_callback_index)

        # 容量约束
        def demand_callback(from_index):
            from_node = self.manager.IndexToNode(from_index)
            return int(self.demands[from_node])

        demand_callback_index = self.routing.RegisterUnaryTransitCallback(demand_callback)
        self.routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
            [int(self.vehicle_capacity)] * num_vehicles,
            True,
            "Capacity"
        )

    def solve(
        self,
        num_vehicles: int,
        depot: int = 0,
        time_limit_seconds: int = 60
    ) -> Optional[Dict]:
        """
        求解CVRP

        Args:
            num_vehicles: 车辆数量
            depot: 仓库节点索引
            time_limit_seconds: 最大求解时间

        Returns:
            求解结果字典，失败返回None
        """
        self._create_model(num_vehicles, depot)

        # 求解参数
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = time_limit_seconds

        # 求解
        self.solution = self.routing.SolveWithParameters(search_parameters)

        if not self.solution:
            return None

        # 提取路线
        self._extract_routes(num_vehicles, depot)

        return self._build_result()

    def _extract_routes(self, num_vehicles: int, depot: int):
        """提取各车辆的路线"""
        self.routes = []

        for vehicle_id in range(num_vehicles):
            index = self.routing.Start(vehicle_id)
            route = []

            while not self.routing.IsEnd(index):
                node = self.manager.IndexToNode(index)
                route.append(node)
                index = self.solution.Value(self.routing.NextVar(index))

            # 路线不为空
            if len(route) > 1:  # 大于1表示有实际访问
                self.routes.append(route)

    def _extract_detailed_route(self, route: List[int]) -> Dict:
        """计算路线详细碳排放"""
        params = get_vehicle_params(self.vehicle_type)
        emission_factor = params["emission_factor"]  # kg CO₂/吨·km

        segments = []
        total_distance = 0.0
        total_carbon = 0.0
        current_load_ton = self.vehicle_capacity / 1000  # 转换为吨

        for i in range(len(route) - 1):
            from_node = route[i]
            to_node = route[i + 1]

            distance = self.distance_matrix[from_node][to_node]

            # 碳排放 = distance × emission_factor × load_ton
            carbon = distance * emission_factor * current_load_ton

            segments.append({
                "from": from_node,
                "to": to_node,
                "distance_km": distance,
                "load_before_ton": current_load_ton,
                "demand_kg": self.demands[to_node],
                "load_after_ton": current_load_ton - self.demands[to_node] / 1000,
                "carbon_kg": carbon
            })

            total_distance += distance
            total_carbon += carbon

            # 卸货
            current_load_ton -= self.demands[to_node] / 1000
            current_load -= self.demands[to_node]

        return {
            "route": route,
            "segments": segments,
            "total_distance_km": total_distance,
            "total_carbon_kg": total_carbon,
            "vehicle_type": self.vehicle_type
        }

    def _build_result(self) -> Dict:
        """构建结果字典"""
        route_details = []
        total_distance = 0.0
        total_carbon = 0.0

        for route in self.routes:
            detail = self._extract_detailed_route(route)
            route_details.append(detail)
            total_distance += detail["total_distance_km"]
            total_carbon += detail["total_carbon_kg"]

        return {
            "success": True,
            "routes": self.routes,
            "route_details": route_details,
            "total_distance_km": total_distance,
            "total_carbon_kg": total_carbon,
            "num_vehicles_used": len(self.routes),
            "vehicle_type": self.vehicle_type,
            "vehicle_capacity": self.vehicle_capacity
        }


def solve_green_cvrp(
    distance_matrix: List[List[float]],
    demands: List[float],
    vehicle_capacity: float,
    num_vehicles: Optional[int] = None,
    vehicle_type: str = "diesel_heavy",
    depot: int = 0,
    time_limit_seconds: int = 60
) -> Optional[Dict]:
    """
    求解Green CVRP（最小化碳排放）

    Args:
        distance_matrix: N×N距离矩阵（公里）
        demands: 各节点需求量（千克），索引0为仓库
        vehicle_capacity: 车辆载重上限
        num_vehicles: 车辆数量，不指定则自动确定
        vehicle_type: 车辆类型
        depot: 仓库节点索引
        time_limit_seconds: 最大求解时间

    Returns:
        求解结果字典
    """
    n = len(distance_matrix)

    # 如果未指定车辆数，使用最小可行数量
    if num_vehicles is None:
        total_demand = sum(demands)
        num_vehicles = max(1, int(np.ceil(total_demand / vehicle_capacity)))
        num_vehicles = min(num_vehicles, n - 1)

    # 尝试求解
    solver = GreenCVRP(
        distance_matrix=distance_matrix,
        demands=demands,
        vehicle_capacity=vehicle_capacity,
        vehicle_type=vehicle_type
    )

    result = solver.solve(
        num_vehicles=num_vehicles,
        depot=depot,
        time_limit_seconds=time_limit_seconds
    )

    if result:
        return result

    # 如果失败，尝试更多车辆
    if num_vehicles < n - 1:
        for extra in range(1, min(5, n - num_vehicles)):
            result = solver.solve(
                num_vehicles=num_vehicles + extra,
                depot=depot,
                time_limit_seconds=time_limit_seconds
            )
            if result:
                return result

    return None


def optimize_vehicle_count(
    distance_matrix: List[List[float]],
    demands: List[float],
    vehicle_capacity: float,
    vehicle_type: str = "diesel_heavy",
    depot: int = 0
) -> Dict:
    """
    优化车辆数量，找到碳排放最优的车队规模

    Args:
        distance_matrix: 距离矩阵
        demands: 需求量
        vehicle_capacity: 车辆容量
        vehicle_type: 车辆类型
        depot: 仓库索引

    Returns:
        最优结果
    """
    n = len(distance_matrix)
    total_demand = sum(demands)
    min_vehicles = max(1, int(np.ceil(total_demand / vehicle_capacity)))
    max_vehicles = min(min_vehicles * 2, n - 1)

    best_result = None
    best_carbon = float("inf")

    print(f"[车队优化] 尝试 {min_vehicles} 到 {max_vehicles} 辆车")

    for nv in range(min_vehicles, max_vehicles + 1):
        result = solve_green_cvrp(
            distance_matrix=distance_matrix,
            demands=demands,
            vehicle_capacity=vehicle_capacity,
            num_vehicles=nv,
            vehicle_type=vehicle_type,
            depot=depot,
            time_limit_seconds=30
        )

        if result:
            carbon = result["total_carbon_kg"]
            print(f"  车辆数={nv}: 碳排放={carbon:.2f}kg, 距离={result['total_distance_km']:.2f}km")

            if carbon < best_carbon:
                best_carbon = carbon
                best_result = result
                best_result["num_vehicles_tested"] = nv

    return best_result or {"error": "No solution found"}


def print_vrp_result(result: Dict, node_names: Optional[List[str]] = None) -> None:
    """打印VRP求解结果"""
    if "error" in result:
        print(f"[VRP求解] 错误: {result['error']}")
        return

    print("\n" + "=" * 70)
    print("Green CVRP 求解结果 - 最小化碳排放")
    print("=" * 70)

    print(f"\n🚛 使用车辆数: {result['num_vehicles_used']}")
    print(f"📏 总行驶距离: {result['total_distance_km']:.2f} km")
    print(f"🌿 总碳排放: {result['total_carbon_kg']:.2f} kg CO2")
    print(f"⛽ 平均碳效率: {result['total_carbon_kg'] / result['total_distance_km']:.4f} kg CO2/km")
    print(f"🚗 车辆类型: {result['vehicle_type']}")
    print(f"📦 车辆容量: {result['vehicle_capacity']:.0f} kg")

    print("\n--- 各车辆路线详情 ---")

    for i, detail in enumerate(result["route_details"]):
        route = detail["route"]

        # 转换节点名称
        if node_names:
            route_str = " -> ".join([node_names.get(n, f"V{n}") for n in route])
        else:
            route_str = " -> ".join([f"V{n}" for n in route])

        print(f"\n🚚 车辆 {i + 1}:")
        print(f"   路线: {route_str}")
        print(f"   距离: {detail['total_distance_km']:.2f} km")
        print(f"   碳排放: {detail['total_carbon_kg']:.2f} kg CO2")

        for seg in detail["segments"]:
            from_name = node_names[seg["from"]] if node_names else f"V{seg['from']}"
            to_name = node_names[seg["to"]] if node_names else f"V{seg['to']}"

            print(f"     {from_name} → {to_name}: "
                  f"{seg['distance_km']:.2f}km, "
                  f"载重{seg['load_before_kg']:.0f}kg→{seg['load_after_kg']:.0f}kg, "
                  f"碳排放{seg['carbon_kg']:.2f}kg")

    # 环保等价物
    total_carbon = result['total_carbon_kg']
    trees = total_carbon / 1825
    print(f"\n🌱 环保等价: 相当于种植 {trees:.1f} 棵树一年吸收量")


if __name__ == "__main__":
    # 测试用例
    print("=== Green CVRP 求解器测试 ===\n")

    # 5节点测试：0=仓库, 1-4=场馆
    test_matrix = [
        [0.0, 5.2, 8.1, 6.3, 9.5],   # 仓库
        [5.2, 0.0, 6.8, 4.2, 7.1],   # 场馆1
        [8.1, 6.8, 0.0, 9.3, 5.6],   # 场馆2
        [6.3, 4.2, 9.3, 0.0, 8.4],   # 场馆3
        [9.5, 7.1, 5.6, 8.4, 0.0],   # 场馆4
    ]

    # 各节点需求量（千克）
    test_demands = [0, 2000, 3000, 1500, 2500]  # 仓库需求为0

    test_names = {0: "仓库", 1: "场馆A", 2: "场馆B", 3: "场馆C", 4: "场馆D"}

    print("节点: ", test_names)
    print("需求量(kg):", test_demands)
    print("距离矩阵:")
    for i, row in enumerate(test_matrix):
        print(f"  {test_names[i]}: {row}")
    print()

    # 求解
    result = solve_green_cvrp(
        distance_matrix=test_matrix,
        demands=test_demands,
        vehicle_capacity=10000,  # 10吨
        num_vehicles=2,
        vehicle_type="diesel_heavy",
        time_limit_seconds=30
    )

    # 打印结果
    print_vrp_result(result, test_names)

    # 优化车辆数
    print("\n\n=== 车辆数优化测试 ===")
    opt_result = optimize_vehicle_count(
        distance_matrix=test_matrix,
        demands=test_demands,
        vehicle_capacity=10000,
        vehicle_type="diesel_heavy"
    )

    if "error" not in opt_result:
        print(f"\n最优: {opt_result['num_vehicles_used']}辆车, "
              f"碳排放={opt_result['total_carbon_kg']:.2f}kg")
