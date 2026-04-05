# 大型赛事绿色物流碳足迹优化平台

基于 Streamlit 的 15运会赛事物流碳排放智能分析与路径优化系统

## 功能模块

- 碳排放实时监控与预测
- VRP路径优化（最小化碳排放）
- 加权K-Means中转仓选址
- 新能源车队配置优化

## 8步使用流程

1. 仓库设置 - 配置总仓库地址和坐标
2. 场馆录入 - 批量导入或逐条添加赛事场馆
3. 物资需求 - 为各场馆录入物资配送需求
4. 车辆配置 - 从车型库选择车辆并配置参数
5. 碳排放分析 - 基于车型库的碳排放对比分析
6. 碳排放概览 - 赛事物流碳足迹实时监控
7. 路径优化 - 执行物流网络优化计算
8. 优化结果 - 查看优化详细结果

## 技术栈

- Streamlit - Web应用框架
- Folium + Streamlit-Folium - 地理信息可视化
- Plotly - 数据可视化
- OR-Tools - CVRP求解
- Scikit-learn - K-Means选址
- 高德地图API - 地理编码/路径规划

## 本地运行

```bash
cd green-logistics-platform
pip install -r requirements.txt
streamlit run app.py
```

## 部署到 Streamlit Cloud

1. 将代码推送到 GitHub 仓库
2. 访问 https://share.streamlit.io/
3. 点击 "New app"
4. 选择你的 GitHub 仓库
5. 选择分支和主文件路径 (app.py)
6. 点击 "Deploy"

## 配置高德API密钥

在 Streamlit Cloud 的 Settings → Secrets 中添加：

```toml
AMAP_API_KEY = "your_amap_api_key"
```
