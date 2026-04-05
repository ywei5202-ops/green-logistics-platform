"""加权K-Means聚类模块 - 用于中转仓选址"""
import numpy as np
from typing import List, Tuple, Dict, Optional
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import warnings

warnings.filterwarnings("ignore")


class WeightedKMeans:
    """加权K-Means聚类器"""

    def __init__(self, n_clusters: int = 3):
        self.n_clusters = n_clusters
        self.centers_ = None
        self.labels_ = None
        self.cluster_weights_ = None

    def fit(
        self,
        coords: List[Tuple[float, float]],
        weights: List[float]
    ) -> "WeightedKMeans":
        """
        执行加权K-Means聚类

        Args:
            coords: 坐标列表 [(lng, lat), ...]
            weights: 每个点的权重（通常为物资需求量）

        Returns:
            self
        """
        coords_array = np.array(coords)
        weights_array = np.array(weights)

        # 归一化权重
        if weights_array.sum() > 0:
            weights_normalized = weights_array / weights_array.sum() * len(weights)
        else:
            weights_normalized = np.ones_like(weights_array)

        # 样本权重用于K-Means
        sample_weight = weights_normalized

        # 执行K-Means
        kmeans = KMeans(
            n_clusters=self.n_clusters,
            init="k-means++",
            n_init=10,
            max_iter=300,
            random_state=42
        )
        kmeans.fit(coords_array, sample_weight=sample_weight)

        self.centers_ = kmeans.cluster_centers_
        self.labels_ = kmeans.labels_
        self.cluster_weights_ = self._calc_cluster_weights(weights_array)

        return self

    def _calc_cluster_weights(self, weights: np.ndarray) -> List[float]:
        """计算每个簇的权重和"""
        cluster_weights = [0.0] * self.n_clusters
        for label, weight in zip(self.labels_, weights):
            cluster_weights[label] += weight
        return cluster_weights

    def get_centers(self) -> List[Tuple[float, float]]:
        """获取聚类中心坐标"""
        if self.centers_ is None:
            return []
        return [(float(center[0]), float(center[1])) for center in self.centers_]

    def get_labels(self) -> List[int]:
        """获取每个点的簇标签"""
        return self.labels_.tolist() if self.labels_ is not None else []

    def get_cluster_weights(self) -> List[float]:
        """获取每个簇的权重和"""
        return self.cluster_weights_


def evaluate_clustering(
    coords: List[Tuple[float, float]],
    weights: List[float],
    k_range: range = range(2, 7)
) -> Dict:
    """
    评估不同K值的聚类效果

    Args:
        coords: 坐标列表
        weights: 权重列表
        k_range: K值范围

    Returns:
        评估结果字典，包含每个K值的轮廓系数
    """
    coords_array = np.array(coords)
    weights_array = np.array(weights)

    results = {}

    for k in k_range:
        try:
            kmeans = WeightedKMeans(n_clusters=k)
            kmeans.fit(coords, weights)

            # 计算轮廓系数（需要加权样本）
            labels = kmeans.get_labels()

            if len(set(labels)) > 1:  # 需要至少2个簇
                # 对于加权数据，使用样本权重
                silhouette = silhouette_score(
                    coords_array,
                    labels,
                    sample_weight=weights_array
                )
            else:
                silhouette = -1.0

            results[k] = {
                "silhouette": silhouette,
                "centers": kmeans.get_centers(),
                "labels": labels,
                "cluster_weights": kmeans.get_cluster_weights()
            }

            print(f"[K={k}] 轮廓系数: {silhouette:.4f}, 簇权重: {kmeans.get_cluster_weights()}")

        except Exception as e:
            print(f"[K={k}] 评估失败: {e}")
            results[k] = {"silhouette": -1.0, "error": str(e)}

    return results


def find_optimal_k(
    coords: List[Tuple[float, float]],
    weights: List[float],
    k_range: range = range(2, 7)
) -> Dict:
    """
    找到最优K值

    Args:
        coords: 坐标列表
        weights: 权重列表
        k_range: K值范围

    Returns:
        最优K值及相关信息
    """
    results = evaluate_clustering(coords, weights, k_range)

    # 过滤有效结果
    valid_results = {k: v for k, v in results.items() if "silhouette" in v}

    if not valid_results:
        return {"optimal_k": 2, "error": "No valid clustering found"}

    # 选择轮廓系数最高的K值
    optimal_k = max(valid_results.keys(), key=lambda k: valid_results[k]["silhouette"])
    optimal_result = valid_results[optimal_k]

    print(f"\n=== 最优K值: {optimal_k} ===")
    print(f"轮廓系数: {optimal_result['silhouette']:.4f}")
    print(f"聚类中心: {optimal_result['centers']}")

    return {
        "optimal_k": optimal_k,
        "silhouette": optimal_result["silhouette"],
        "centers": optimal_result["centers"],
        "labels": optimal_result["labels"],
        "cluster_weights": optimal_result["cluster_weights"],
        "all_results": valid_results
    }


def select_warehouse_locations(
    coords: List[Tuple[float, float]],
    weights: List[float],
    max_warehouses: int = 6
) -> Dict:
    """
    中转仓选址主函数

    Args:
        coords: 场馆坐标列表 [(lng, lat), ...]
        weights: 各场馆物资需求量 [kg, ...]
        max_warehouses: 最大仓库数量上限

    Returns:
        {
            "optimal_k": 最优仓库数,
            "warehouses": [{"lng":, "lat":, "weight":, "venues": [...]}],
            "venue_assignments": [{"venue_idx":, "warehouse_idx":, "coord":, "weight":}, ...]
        }
    """
    if len(coords) < 2:
        return {
            "optimal_k": 1,
            "warehouses": [{"lng": coords[0][0], "lat": coords[0][1], "weight": sum(weights), "venues": list(range(len(coords)))}],
            "venue_assignments": [{"venue_idx": i, "warehouse_idx": 0, "coord": coords[i], "weight": weights[i]} for i in range(len(coords))]
        }

    # 评估K=1到K=max_warehouses
    k_range = range(1, min(max_warehouses + 1, len(coords)))

    print(f"[中转仓选址] 开始评估 K={k_range.start} 到 K={k_range.stop-1}")

    result = find_optimal_k(coords, weights, k_range)

    optimal_k = result["optimal_k"]
    centers = result["centers"]
    labels = result["labels"]

    # 构建仓库信息
    warehouses = []
    for i, center in enumerate(centers):
        warehouse_venues = [idx for idx, label in enumerate(labels) if label == i]
        warehouse_weight = sum(weights[idx] for idx in warehouse_venues)

        warehouses.append({
            "warehouse_idx": i,
            "lng": center[0],
            "lat": center[1],
            "weight": warehouse_weight,
            "venue_count": len(warehouse_venues),
            "venues": warehouse_venues
        })

    # 构建场馆分配信息
    venue_assignments = []
    for idx, (coord, weight) in enumerate(zip(coords, weights)):
        warehouse_idx = labels[idx]
        venue_assignments.append({
            "venue_idx": idx,
            "warehouse_idx": warehouse_idx,
            "coord": coord,
            "weight": weight,
            "warehouse_coord": centers[warehouse_idx]
        })

    return {
        "optimal_k": optimal_k,
        "silhouette": result["silhouette"],
        "warehouses": warehouses,
        "venue_assignments": venue_assignments,
        "total_weight": sum(weights),
        "all_evaluation_results": result.get("all_results", {})
    }


def print_clustering_report(result: Dict) -> None:
    """打印聚类选址报告"""
    print("\n" + "=" * 60)
    print("中转仓选址报告")
    print("=" * 60)

    print(f"\n最优仓库数量: {result['optimal_k']}")
    print(f"轮廓系数: {result.get('silhouette', 0):.4f}")
    print(f"总物资量: {result['total_weight']:,.0f} kg")

    print("\n--- 仓库详情 ---")
    for wh in result["warehouses"]:
        print(f"\n仓库 {wh['warehouse_idx'] + 1}:")
        print(f"  坐标: ({wh['lng']:.6f}, {wh['lat']:.6f})")
        print(f"  覆盖场馆数: {wh['venue_count']}")
        print(f"  物资总量: {wh['weight']:,.0f} kg")
        print(f"  覆盖场馆索引: {wh['venues']}")

    print("\n--- 场馆分配 ---")
    for va in result["venue_assignments"]:
        print(f"场馆{va['venue_idx']}: 分配到仓库{va['warehouse_idx']+1}, "
              f"坐标({va['coord'][0]:.4f}, {va['coord'][1]:.4f}), "
              f"需求{va['weight']:.0f}kg")


if __name__ == "__main__":
    # 测试用例
    print("=== 加权K-Means中转仓选址测试 ===\n")

    # 5个测试场馆
    test_venues = [
        (113.2644, 23.1291),  # 场馆0
        (113.2750, 23.1320),  # 场馆1
        (113.2600, 23.1350),  # 场馆2
        (113.2680, 23.1250),  # 场馆3
        (113.2800, 23.1280),  # 场馆4
    ]

    # 各场馆物资需求（吨）
    test_weights = [3000, 5000, 2000, 4000, 1500]

    print("测试场馆坐标:", test_venues)
    print("测试物资需求(kg):", test_weights)
    print()

    # 执行选址
    result = select_warehouse_locations(test_venues, test_weights, max_warehouses=5)

    # 打印报告
    print_clustering_report(result)

    # 评估不同K值
    print("\n\n=== K值评估结果 ===")
    for k, v in result.get("all_evaluation_results", {}).items():
        sil = v.get("silhouette", -1)
        marker = " <-- 最优" if k == result["optimal_k"] else ""
        print(f"K={k}: 轮廓系数={sil:.4f}{marker}")
