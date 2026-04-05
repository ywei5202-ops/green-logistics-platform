"""距离矩阵构建模块 - 调用高德API构建N×N距离矩阵，支持缓存和进度回调"""
import json
import os
import hashlib
import time
from typing import List, Tuple, Dict, Optional, Callable
import requests

# 高德API请求频率限制：每秒不超过10次
_request_timestamps: List[float] = []
_RATE_LIMIT = 10
_lock_active = False


def _acquire_rate_limit() -> None:
    """获取请求令牌，超过限制则等待"""
    global _request_timestamps, _lock_active
    current_time = time.time()

    # 清理1秒前的所有时间戳
    _request_timestamps = [ts for ts in _request_timestamps if current_time - ts < 1.0]

    if len(_request_timestamps) >= _RATE_LIMIT:
        sleep_time = 1.0 - (current_time - _request_timestamps[0])
        if sleep_time > 0:
            time.sleep(sleep_time)
        current_time = time.time()
        _request_timestamps = [ts for ts in _request_timestamps if current_time - ts < 1.0]

    _request_timestamps.append(time.time())


def _generate_cache_key(coords: List[Tuple[float, float]]) -> str:
    """根据坐标列表生成缓存文件名的hash"""
    coord_str = ";".join([f"{lng},{lat}" for lng, lat in coords])
    return hashlib.md5(coord_str.encode()).hexdigest()


def _get_cache_path(cache_key: str) -> str:
    """获取缓存文件路径"""
    cache_dir = "data/cache"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"distance_matrix_{cache_key}.json")


def _save_cache(cache_path: str, matrix: Dict) -> None:
    """保存矩阵到缓存文件"""
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)


def _load_cache(cache_path: str) -> Optional[Dict]:
    """从缓存文件加载矩阵"""
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def build_distance_matrix(
    coords: List[Tuple[float, float]],
    api_key: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    use_cache: bool = True
) -> Optional[List[List[float]]]:
    """
    构建N×N距离矩阵

    Args:
        coords: 坐标列表，每个元素为 (lng, lat)
        api_key: 高德地图API密钥
        progress_callback: 进度回调函数，签名为 (progress: float, message: str) -> None
        use_cache: 是否使用缓存（默认True）

    Returns:
        N×N距离矩阵（公里），失败返回None
    """
    if not coords or len(coords) < 2:
        print("[距离矩阵] 错误: 坐标列表为空或少于2个点")
        return None

    n = len(coords)

    # 检查缓存
    if use_cache:
        cache_key = _generate_cache_key(coords)
        cache_path = _get_cache_path(cache_key)
        cached = _load_cache(cache_path)
        if cached and cached.get("n") == n:
            print(f"[距离矩阵] 从缓存加载: {cache_path}")
            return cached.get("matrix")

    # 初始化距离矩阵
    distance_matrix = [[0.0] * n for _ in range(n)]

    total_requests = n * (n - 1) // 2  # 上三角矩阵的请求数
    completed = 0

    if progress_callback:
        progress_callback(0.0, f"开始构建 {n}×{n} 距离矩阵，共需 {total_requests} 次API请求...")

    url = "https://restapi.amap.com/v3/direction/driving"

    for i in range(n):
        for j in range(i + 1, n):
            origin = coords[i]
            destination = coords[j]

            params = {
                "key": api_key,
                "origin": f"{origin[0]},{origin[1]}",
                "destination": f"{destination[0]},{destination[1]}"
            }

            success = False
            for retry in range(3):
                try:
                    _acquire_rate_limit()
                    response = requests.get(url, params=params, timeout=10)
                    data = response.json()

                    if data.get("status") == "1" and data.get("route", {}).get("paths"):
                        distance = float(data["route"]["paths"][0]["distance"]) / 1000  # 米转公里
                        distance_matrix[i][j] = distance
                        distance_matrix[j][i] = distance  # 对称
                        success = True
                    else:
                        errcode = data.get("errcode", "")
                        errmsg = data.get("errmsg", "未知错误")
                        print(f"[距离矩阵] API错误 ({i},{j}): {errcode} - {errmsg}")

                    break  # 成功或API错误，不再重试

                except requests.exceptions.Timeout:
                    print(f"[距离矩阵] 请求超时 ({i},{j})，重试 {retry + 1}/3")
                    time.sleep(1)

                except requests.exceptions.ConnectionError:
                    print(f"[距离矩阵] 网络错误 ({i},{j})，重试 {retry + 1}/3")
                    time.sleep(2)

                except Exception as e:
                    print(f"[距离矩阵] 未知错误 ({i},{j}): {e}")
                    break

            if not success:
                # 使用Haversine距离作为fallback
                from utils.amap_api import haversine_distance
                fallback_dist = haversine_distance(origin, destination)
                distance_matrix[i][j] = fallback_dist
                distance_matrix[j][i] = fallback_dist
                print(f"[距离矩阵] 使用Haversine fallback: {fallback_dist:.2f}km")

            completed += 1

            # 进度回调
            if progress_callback:
                progress = completed / total_requests
                msg = f"处理中: ({i},{j}) - {completed}/{total_requests}"
                progress_callback(progress, msg)

    # 保存缓存
    if use_cache:
        cache_data = {
            "n": n,
            "coords": coords,
            "matrix": distance_matrix
        }
        _save_cache(cache_path, cache_data)
        print(f"[距离矩阵] 缓存已保存: {cache_path}")

    if progress_callback:
        progress_callback(1.0, "距离矩阵构建完成！")

    return distance_matrix


def build_time_matrix(
    coords: List[Tuple[float, float]],
    api_key: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    use_cache: bool = True
) -> Optional[List[List[float]]]:
    """
    构建N×N时间矩阵（分钟）

    Args:
        coords: 坐标列表，每个元素为 (lng, lat)
        api_key: 高德地图API密钥
        progress_callback: 进度回调函数
        use_cache: 是否使用缓存

    Returns:
        N×N时间矩阵（分钟），失败返回None
    """
    if not coords or len(coords) < 2:
        print("[时间矩阵] 错误: 坐标列表为空或少于2个点")
        return None

    n = len(coords)

    # 检查缓存
    if use_cache:
        cache_key = _generate_cache_key(coords) + "_time"
        cache_path = _get_cache_path(cache_key)
        cached = _load_cache(cache_path)
        if cached and cached.get("n") == n:
            print(f"[时间矩阵] 从缓存加载: {cache_path}")
            return cached.get("matrix")

    # 初始化时间矩阵
    time_matrix = [[0.0] * n for _ in range(n)]

    total_requests = n * (n - 1) // 2
    completed = 0

    if progress_callback:
        progress_callback(0.0, f"开始构建 {n}×{n} 时间矩阵...")

    url = "https://restapi.amap.com/v3/direction/driving"

    for i in range(n):
        for j in range(i + 1, n):
            origin = coords[i]
            destination = coords[j]

            params = {
                "key": api_key,
                "origin": f"{origin[0]},{origin[1]}",
                "destination": f"{destination[0]},{destination[1]}"
            }

            success = False
            for retry in range(3):
                try:
                    _acquire_rate_limit()
                    response = requests.get(url, params=params, timeout=10)
                    data = response.json()

                    if data.get("status") == "1" and data.get("route", {}).get("paths"):
                        duration = float(data["route"]["paths"][0]["duration"]) / 60  # 秒转分钟
                        time_matrix[i][j] = duration
                        time_matrix[j][i] = duration
                        success = True
                    break

                except Exception as e:
                    print(f"[时间矩阵] 错误 ({i},{j}): {e}")
                    break

            if not success:
                # 使用估算：假设平均速度30km/h
                from utils.amap_api import haversine_distance
                dist = haversine_distance(origin, destination)
                time_matrix[i][j] = dist / 30 * 60  # 分钟
                time_matrix[j][i] = time_matrix[i][j]

            completed += 1

            if progress_callback:
                progress_callback(completed / total_requests, f"处理中: ({i},{j})")

    # 保存缓存
    if use_cache:
        cache_data = {
            "n": n,
            "coords": coords,
            "matrix": time_matrix
        }
        _save_cache(cache_path, cache_data)

    if progress_callback:
        progress_callback(1.0, "时间矩阵构建完成！")

    return time_matrix


def get_matrix_info(matrix: List[List[float]]) -> Dict:
    """获取矩阵统计信息"""
    n = len(matrix)
    if n == 0:
        return {"size": 0, "total": 0, "avg": 0, "max": 0, "min": 0}

    values = []
    for i in range(n):
        for j in range(i + 1, n):
            values.append(matrix[i][j])

    return {
        "size": f"{n}×{n}",
        "total": sum(values),
        "avg": sum(values) / len(values) if values else 0,
        "max": max(values) if values else 0,
        "min": min(values) if values else 0
    }


if __name__ == "__main__":
    # 测试用例
    print("=== 距离矩阵模块测试 ===")

    test_coords = [
        (113.2644, 23.1291),  # 仓库
        (113.2650, 23.1320),  # 场馆1
        (113.2700, 23.1280),  # 场馆2
        (113.2600, 23.1350),  # 场馆3
        (113.2680, 23.1250),  # 场馆4
    ]

    def progress(prog: float, msg: str):
        print(f"[进度 {prog*100:.1f}%] {msg}")

    # 注意：需要有效的API Key才能测试
    # matrix = build_distance_matrix(test_coords, "YOUR_API_KEY", progress_callback=progress)

    print("测试坐标:", test_coords)
    print("矩阵大小:", len(test_coords), "×", len(test_coords))
    print("API Key未提供，跳过实际API调用测试")
