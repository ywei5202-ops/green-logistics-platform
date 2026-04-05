"""碳排放计算工具模块"""
from typing import Dict, List, Optional
import pandas as pd


# 碳排放因子 (kg CO2/L or kg CO2/kWh)
EMISSION_FACTORS = {
    "diesel": 2.68,
    "gasoline": 2.31,
    "electric": 0.0,  # 电网碳排放因子需另行计算
    "hybrid": 1.5,
    "natural_gas": 2.0,
}

# 燃油消耗因子 (L/100km)
FUEL_CONSUMPTION = {
    "light_truck": 12.0,
    "medium_truck": 18.0,
    "heavy_truck": 25.0,
    "van": 10.0,
    "electric_van": 25.0,  # kWh/100km
}

# 电动物流车碳排放因子 (kg CO2/kWh) - 电网平均
GRID_CARBON_INTENSITY = 0.6


def calc_fuel_emission(
    distance_km: float,
    vehicle_type: str = "medium_truck",
    fuel_type: str = "diesel"
) -> float:
    """计算燃油车的碳排放量 (kg CO2)"""
    if fuel_type == "electric":
        return calc_electric_emission(distance_km, vehicle_type)

    fuel_consumption = FUEL_CONSUMPTION.get(vehicle_type, 18.0)
    emission_factor = EMISSION_FACTORS.get(fuel_type, 2.68)

    fuel_used = distance_km * fuel_consumption / 100
    return fuel_used * emission_factor


def calc_electric_emission(distance_km: float, vehicle_type: str = "electric_van") -> float:
    """计算电动物流车的碳排放量 (kg CO2)"""
    electricity_consumption = FUEL_CONSUMPTION.get(vehicle_type, 25.0)
    electricity_used = distance_km * electricity_consumption / 100
    return electricity_used * GRID_CARBON_INTENSITY


def calc_route_carbon(
    distance_km: float,
    load_kg: float = 0,
    vehicle_type: str = "medium_truck"
) -> float:
    """考虑载重的碳排放计算 (kg CO2)"""
    base_emission = calc_fuel_emission(distance_km, vehicle_type)

    load_factor = 1.0 + (load_kg / 10000) * 0.1

    return base_emission * load_factor


def calc_total_carbon(
    route_distances: List[float],
    route_loads: List[float],
    vehicle_type: str = "medium_truck"
) -> Dict[str, float]:
    """计算总碳排放"""
    total_distance = sum(route_distances)
    emissions = [
        calc_route_carbon(d, l, vehicle_type)
        for d, l in zip(route_distances, route_loads)
    ]
    total_emission = sum(emissions)

    return {
        "total_distance_km": total_distance,
        "total_carbon_kg": total_emission,
        "avg_carbon_per_km": total_emission / total_distance if total_distance > 0 else 0,
        "route_count": len(route_distances)
    }


def carbon_to_trees(carbon_kg: float) -> float:
    """将碳排放量转换为需要种植的树木数量（每天吸收5kg CO2）"""
    annual_absorption = 5 * 365
    return carbon_kg / annual_absorption


def get_carbon_intensity_label(carbon_per_km: float) -> str:
    """获取碳排放强度标签"""
    if carbon_per_km < 0.5:
        return "🟢 优秀"
    elif carbon_per_km < 1.0:
        return "🟡 良好"
    elif carbon_per_km < 1.5:
        return "🟠 一般"
    else:
        return "🔴 需优化"


def generate_carbon_report(df_routes: pd.DataFrame) -> pd.DataFrame:
    """生成碳排放报告DataFrame"""
    df = df_routes.copy()
    df["碳排放量_kg"] = df.apply(
        lambda row: calc_route_carbon(
            row.get("distance_km", 0),
            row.get("load_kg", 0),
            row.get("vehicle_type", "medium_truck")
        ), axis=1
    )
    df["碳排放等级"] = df["碳排放量_kg"].apply(
        lambda x: get_carbon_intensity_label(x / max(df_routes.get("distance_km", [1])[df_routes.index], 1))
    )
    return df
