"""碳排放计算引擎

公式：E = distance_km × emission_factor × load_tons
支持载重动态递减（逐站卸货后载重减少）
"""
from typing import List, Tuple, Dict, Optional
import json


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
    """获取车型碳排放参数"""
    global _vehicle_types_cache
    if _vehicle_types_cache is None:
        _vehicle_types_cache = {v["id"]: v for v in load_vehicle_types()}

    vehicle = _vehicle_types_cache.get(vehicle_type_id, {})
    return {
        "emission_factor": vehicle.get("emission_factor_default", 0.060),  # kg CO₂/吨·km
        "max_load_ton": vehicle.get("max_load_ton_default", 15.0),
        "fuel_consumption": vehicle.get("fuel_consumption", "N/A")
    }


# 默认车辆参数
DEFAULT_VEHICLE = {
    "emission_factor": 0.060,  # kg CO₂/吨·km
    "max_load_ton": 15.0,
    "fuel_consumption": "25-38 L柴油/100km"
}


class CarbonCalculator:
    """碳排放计算器"""

    def __init__(self, vehicle_type: str = "diesel_heavy"):
        """
        初始化碳排放计算器

        Args:
            vehicle_type: 车辆类型ID，如"diesel_heavy", "bev"等
        """
        self.vehicle_type = vehicle_type
        self.vehicle_params = get_vehicle_params(vehicle_type)
        self.emission_factor = self.vehicle_params["emission_factor"]  # kg CO₂/吨·km
        self.max_load_ton = self.vehicle_params["max_load_ton"]

    def calc_emission(
        self,
        distance_km: float,
        load_kg: float
    ) -> float:
        """
        计算单程碳排放

        公式: E = distance_km × emission_factor × load_ton

        Args:
            distance_km: 行驶距离（公里）
            load_kg: 当前载重（千克）

        Returns:
            碳排放量（kg CO2）
        """
        if distance_km <= 0 or load_kg <= 0:
            return 0.0

        load_ton = load_kg / 1000
        carbon = distance_km * self.emission_factor * load_ton

        return carbon

        return carbon

    def calc_emission_with_load_decay(
        self,
        route: List[Tuple[int, float]],
        demands: List[float],
        vehicle_capacity: float
    ) -> Dict:
        """
        计算路线碳排放（考虑逐站卸货后载重递减）

        Args:
            route: 路线节点列表，如 [(node_idx, remaining_load), ...]
                  起点为depot，节点按访问顺序排列
            demands: 各节点需求量（千克）
            vehicle_capacity: 车辆最大载重（千克）

        Returns:
            {
                "total_carbon_kg": 总碳排放,
                "segments": [{"from":, "to":, "distance_km":, "load_kg":, "carbon_kg":}, ...]
            }
        """
        segments = []
        total_carbon = 0.0

        # 计算每段行程的碳排放
        for i in range(len(route) - 1):
            from_node = route[i]
            to_node = route[i + 1]

            # 从from_node到to_node时，车上还剩的货物
            # 假设我们从depot出发，依次访问各节点
            remaining_load = vehicle_capacity - sum(demands[:to_node]) if to_node > 0 else vehicle_capacity
            remaining_load = max(remaining_load, 0)

            segment_carbon = self.calc_emission(
                distance_km=0,  # 距离需要外部传入
                load_kg=remaining_load
            )

            segments.append({
                "from": from_node,
                "to": to_node,
                "load_kg": remaining_load,
                "carbon_kg": segment_carbon
            })

            total_carbon += segment_carbon

        return {
            "total_carbon_kg": total_carbon,
            "segments": segments
        }


def calc_route_carbon(
    distance_matrix: List[List[float]],
    route: List[int],
    demands: List[float],
    vehicle_type: str = "diesel_heavy",
    vehicle_capacity: float = 10000.0
) -> Dict:
    """
    计算路线碳排放（考虑载重动态递减）

    Args:
        distance_matrix: N×N距离矩阵（公里）
        route: 访问路线节点索引列表，如 [0, 3, 1, 4, 0]（0为仓库）
        demands: 各节点需求量（千克），索引0为仓库（需求为0）
        vehicle_type: 车辆类型ID
        vehicle_capacity: 车辆载重上限（千克）

    Returns:
        {
            "total_distance_km": 总行驶距离,
            "total_carbon_kg": 总碳排放,
            "segments": 各路段详情
        }
    """
    calculator = CarbonCalculator(vehicle_type)
    emission_factor = calculator.emission_factor

    segments = []
    total_distance = 0.0
    total_carbon = 0.0
    current_load_ton = vehicle_capacity / 1000  # 初始载重（吨）

    for i in range(len(route) - 1):
        from_node = route[i]
        to_node = route[i + 1]

        # 获取距离
        distance = distance_matrix[from_node][to_node]

        # 碳排放 = distance × emission_factor × load_ton
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

        # 卸货后载重减少
        current_load_ton -= demands[to_node] / 1000
        current_load_ton = max(current_load_ton, 0)

    return {
        "total_distance_km": total_distance,
        "total_carbon_kg": total_carbon,
        "segments": segments,
        "vehicle_type": vehicle_type,
        "vehicle_capacity": vehicle_capacity
    }
            "distance_km": distance,
            "load_before_kg": current_load,
            "demand_kg": demands[to_node],
            "load_after_kg": current_load - demands[to_node],
            "energy": energy,
            "carbon_kg": carbon
        })

        total_distance += distance
        total_carbon += carbon

        # 卸货后载重减少
        current_load -= demands[to_node]
        current_load = max(current_load, 0)

    return {
        "total_distance_km": total_distance,
        "total_carbon_kg": total_carbon,
        "segments": segments,
        "vehicle_type": vehicle_type,
        "vehicle_capacity": vehicle_capacity
    }


def calc_fleet_carbon(
    distance_matrix: List[List[float]],
    routes: List[List[int]],
    demands: List[float],
    vehicle_type: str = "diesel_heavy",
    vehicle_capacity: float = 10000.0
) -> Dict:
    """
    计算整个车队的总碳排放

    Args:
        distance_matrix: N×N距离矩阵
        routes: 各车辆的路线列表，如 [[0,3,1,0], [0,4,2,0], ...]
        demands: 各节点需求量
        vehicle_type: 车辆类型
        vehicle_capacity: 车辆载重上限

    Returns:
        {
            "total_distance_km": 总距离,
            "total_carbon_kg": 总碳排放,
            "route_count": 路线数,
            "avg_carbon_per_km": 平均每公里碳排放,
            "route_details": 各路线详情
        }
    """
    route_details = []
    total_distance = 0.0
    total_carbon = 0.0

    for i, route in enumerate(routes):
        route_result = calc_route_carbon(
            distance_matrix, route, demands, vehicle_type, vehicle_capacity
        )
        route_details.append({
            "vehicle_id": i,
            "route": route,
            **route_result
        })
        total_distance += route_result["total_distance_km"]
        total_carbon += route_result["total_carbon_kg"]

    return {
        "total_distance_km": total_distance,
        "total_carbon_kg": total_carbon,
        "route_count": len(routes),
        "avg_carbon_per_km": total_carbon / total_distance if total_distance > 0 else 0,
        "route_details": route_details
    }


def carbon_to_equivalents(carbon_kg: float) -> Dict:
    """
    将碳排放转换为环保等价物

    Args:
        carbon_kg: 碳排放量（千克）

    Returns:
        等价物字典
    """
    # 树木每天吸收约5kg CO2，一年约1825kg
    trees_per_year = carbon_kg / 1825

    # 汽油每升燃烧产生约2.3kg CO2
    gasoline_liters = carbon_kg / 2.3

    # 电力每度约产生0.6kg CO2
    electricity_kwh = carbon_kg / 0.6

    return {
        "trees_equivalent": trees_per_year,
        "trees_per_year": round(trees_per_year),
        "gasoline_liters": gasoline_liters,
        "electricity_kwh": electricity_kwh
    }


def print_carbon_report(result: Dict) -> None:
    """打印碳排放报告"""
    print("\n" + "=" * 60)
    print("碳排放计算报告")
    print("=" * 60)

    print(f"\n总行驶距离: {result['total_distance_km']:.2f} km")
    print(f"总碳排放: {result['total_carbon_kg']:.2f} kg CO2")
    print(f"平均碳排放: {result['avg_carbon_per_km']:.4f} kg CO2/km")
    print(f"车辆数: {result['route_count']}")

    print("\n--- 各车辆路线详情 ---")
    for detail in result["route_details"]:
        print(f"\n车辆 {detail['vehicle_id'] + 1}:")
        print(f"  路线: {' -> '.join(map(str, detail['route']))}")
        print(f"  距离: {detail['total_distance_km']:.2f} km")
        print(f"  碳排放: {detail['total_carbon_kg']:.2f} kg CO2")

        for seg in detail["segments"]:
            print(f"    {seg['from']} -> {seg['to']}: {seg['distance_km']:.2f}km, "
                  f"载重{seg['load_before_kg']:.0f}kg -> {seg['load_after_kg']:.0f}kg, "
                  f"碳排放{seg['carbon_kg']:.2f}kg")

    # 环保等价物
    eq = carbon_to_equivalents(result["total_carbon_kg"])
    print(f"\n--- 环保等价物 ---")
    print(f"相当于种植 {eq['trees_per_year']} 棵树一年吸收量")
    print(f"或 {eq['gasoline_liters']:.0f} 升汽油燃烧")
    print(f"或 {eq['electricity_kwh']:.0f} 度电产生")


if __name__ == "__main__":
    # 测试用例
    print("=== 碳排放计算引擎测试 ===\n")

    # 测试距离矩阵（5个节点）
    test_matrix = [
        [0.0, 5.2, 8.1, 6.3, 9.5],
        [5.2, 0.0, 6.8, 4.2, 7.1],
        [8.1, 6.8, 0.0, 9.3, 5.6],
        [6.3, 4.2, 9.3, 0.0, 8.4],
        [9.5, 7.1, 5.6, 8.4, 0.0],
    ]

    # 测试路线
    test_routes = [
        [0, 1, 3, 0],  # 车辆1
        [0, 2, 4, 0],  # 车辆2
    ]

    # 各节点需求量（千克），索引0为仓库
    test_demands = [0, 2000, 3000, 1500, 2500]

    print("距离矩阵:", test_matrix)
    print("路线:", test_routes)
    print("需求量(kg):", test_demands)
    print()

    # 计算碳排放
    result = calc_fleet_carbon(
        distance_matrix=test_matrix,
        routes=test_routes,
        demands=test_demands,
        vehicle_type="diesel_heavy",
        vehicle_capacity=10000.0
    )

    # 打印报告
    print_carbon_report(result)

    # 单段计算测试
    print("\n\n=== 单路段碳排放测试 ===")
    calc = CarbonCalculator("diesel_heavy")
    carbon = calc.calc_emission(distance_km=100, load_kg=5000)
    print(f"100km, 5吨载重: {carbon:.2f} kg CO2")
