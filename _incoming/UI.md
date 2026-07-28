# 海洋科研数据可视化分析平台界面设计说明
## 1. 软件概述
本软件采用 **PyQt 框架开发**，面向海洋与渔业科研人员，设计用于多源海洋数据的快速查询、数据属性查看、时空范围筛选、可视化绘制以及结果导出。

软件采用**单窗口主界面结构**，避免复杂页面跳转，通过三个功能区域完成完整科研数据分析流程：


数据查询
↓
数据属性确认
↓
时间/空间筛选
↓
图形预览
↓
绘制
↓
结果导出

主界面划分为：

1. 数据查询与信息展示区（Find the Data）
2. 图形参数设置与预览区（Make a Graph）
3. 绘图控制与结果导出区（Plot & Export）



# 2. 界面整体布局

主界面采用上下三部分布局：

```

================================================
数据查询与信息展示区域

================================================
绘图参数设置与图像预览区域

================================================
绘制与导出控制区域

================================================

```

---

# 3. 顶部区域：数据查询与信息展示（Find the Data）

## 3.1 初始查询界面

软件启动后默认进入数据查询状态。

界面显示：

```

Find the Data

```

提供数据查询输入框，用于检索目标数据。

功能：

- 支持关键词模糊查询；
- 查询信息来源于 config 配置文件；
- 支持多个数据集同时查询；
- 支持推荐数据下拉选择。

例如：

输入：

```

temperature

```

自动匹配：

```

SST Dataset
Copernicus Temperature
HYCOM Temperature

```

---

## 3.2 推荐数据选择

输入框同时提供常用数据推荐：

```

▼ Dataset Recommendation

Copernicus SST
HYCOM Ocean Current
Chlorophyll-a
ROMS Forecast

```

推荐列表由 config 文件维护，方便后续扩展数据源。

---

## 3.3 查询成功后的信息展示界面

当用户成功查询数据后，上方区域由查询模式切换为数据展示模式。

展示内容包括：

| 信息 | 描述 |
|---|---|
| Dataset Name | 数据集名称 |
| Data Source | 数据来源 |
| Variable | 数据变量 |
| Time Range | 数据时间范围 |
| Spatial Range | 空间覆盖范围 |
| Resolution | 空间分辨率 |
| Depth | 深度层范围 |

示例：

```

Dataset:
cmems_mod_glo_phy

Source:
Copernicus Marine

Variable:
Temperature

Resolution:
0.1°

Depth:
0-300 m

```

---

## 3.4 多数据同时查询与展示

系统支持多个数据集或多个变量同时查询。

例如：

```

Temperature
Salinity
Chlorophyll
Current

```

展示方式采用多个水平排列的信息卡片：

```

---

Dataset 1 Information

Variable:
Temperature

Resolution:
0.1°
----

Dataset 2 Information

Variable:
Chlorophyll

Resolution:
0.25°
-----

```

---

## 3.5 返回查询

信息展示界面右下角设置：

```

Back

```

功能：

- 清除当前查询结果；
- 返回数据查询状态；
- 支持重新选择数据。


---

# 4. 中间区域：绘图参数设置与预览（Make a Graph）

该区域为软件核心交互区域。

采用左右结构：

```

------
Make a Graph
------
                    |
时间空间参数设置     |  图像预览区域
                    |
------

```

---

# 4.1 当前变量选择

由于数据查询支持多个变量，而单幅图像只能显示一个变量，因此在标题区域增加变量选择：

```

Make a Graph

Variable:

▼ Temperature

```

用于切换当前绘制变量。

---

# 4.2 左侧：时间与空间筛选

## 4.2.1 时间筛选（Time Selection）

支持：

### 起止时间选择

起止时间横向排布
```

Start Time:

2025-01-01

End Time:

2025-03-31

```

---

### 时间统计尺度

提供：

```

Daily

Weekly Mean

Monthly Mean

Annual Mean

```

对应：

- 日尺度数据；
- 周平均数据；
- 月平均数据；
- 年平均数据。


---

## 4.2.2 空间筛选（Spatial Selection）

采用经纬度范围控制。使用常见的上下左右四个位置放置四个框，更符合空间直觉。使用config提供常用区域的预裁剪范围。

输入：

```

North Latitude

South Latitude

East Longitude

West Longitude

```

规则：

- 北纬为正；
- 南纬为负；
- 东经为正；
- 西经为负。


示例：

```

North: 25

South: 0

East: 125

West: 105

```

---

## 4.2.3 空间分辨率调整

显示当前数据库默认分辨率：

```

Original Resolution:

0.1°

```

支持用户选择更低空间分辨率：

```

Resolution:

0.1°

0.25°

0.5°

1°

```

最大空间范围和可选分辨率提前存储于 config 文件。

---

# 4.3 右侧：快速预览区域

用于显示低分辨率示例图。

目的：

- 快速确认空间范围；
- 检查数据分布；
- 判断参数设置是否合理。

布局：

```

------

 Preview Map

------


   Colorbar
```



---

## 4.3.1 Colorbar设置

Colorbar 位于图像下方。

旁边提供颜色风格选择：

```

Color Style

▼ viridis

jet

turbo

coolwarm

```

支持不同科研绘图风格。

---

# 5. 底部区域：绘制与导出（Plot & Export）

布局：

```

---

 Plot       Export

---

```

---

# 5.1 绘图功能（Plot）

用户完成：

- 数据选择；
- 时间范围设置；
- 空间范围设置；
- 分辨率设置；
- 当前变量选择；

点击：

```

Plot

```

执行：

1. 数据读取；
2. 时间筛选；
3. 空间裁剪；
4. 分辨率调整；
5. 图像生成。


---

# 5.2 导出功能（Export）

点击：

```

Export

```

进入保存设置。

支持：

## 保存路径

例如：

```

D:/Ocean_Result/

```

---

## 文件格式

支持：

```

PNG

JPG

TIFF

PDF

NetCDF

```

---

## 文件自动命名

格式：

```

Variable_TimeRange_Region

```

示例：

```

SST_20250101-20250331_SCS.png

````

---

# 6. Config 数据管理设计

系统采用配置文件管理数据元信息。

程序不直接固定数据参数，而通过 config 文件读取。

示例：

```yaml
datasets:

  - name: Copernicus SST

    variable:
      - temperature

    resolution:

      default: 0.1

      available:
        - 0.1
        - 0.25
        - 0.5


    spatial:

      lon:
        min: -180
        max: 180

      lat:
        min: -90
        max: 90


    temporal:

      start: 1993

      end: 2026
````

