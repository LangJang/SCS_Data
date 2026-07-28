# ROMS Sigma-to-Z 深度层提取处理文档

## 概述

将 ROMS 日平均输出文件中地形跟随 S 坐标（sigma 坐标）的三维变量插值提取到固定深度层。输出文件**仅包含经过深度插值处理的变量**（含 `depth` 维度），不含静态场、二维时变场和模型标量参数——这些信息请参考原始文件。

- **处理脚本**: `depth_interp.py`
- **输入目录**: `E:\ROMS\daily\2023\`
- **输出目录**: `D:\ROMS\daily\depth_process\`
- **处理日期**: 2026-07-27

---

## 数据源

| 属性 | 值 |
|------|-----|
| **模型** | ROMS/TOMS Version 4.2 |
| **区域** | 南海 (South China Sea) |
| **输入文件** | `roms_avg_YYYYMMDDZ12.nc` (365 个日平均文件) |
| **原始格式** | NetCDF-3, 64-bit offset |
| **原始网格** | 1668 × 2340 (eta_rho × xi_rho), ~2 km |
| **原始垂直坐标** | 45 层地形跟随 S 坐标 (s_rho) + 46 层 W 点 (s_w) |

### 原始空间范围

| 参数 | 最小值 | 最大值 |
|------|--------|--------|
| 经度 | 90.12°E | 133.78°E |
| 纬度 | 0.80°N | 30.38°N |
| 水深 | 5 m | 10081 m |

---

## 处理方法

### 深度计算公式 (Vtransform=2)

$$z(\sigma) = \zeta + (\zeta + h) \cdot \frac{h_c \cdot \sigma + h \cdot C_s(\sigma)}{h_c + h}$$

其中：
- $z$ — 实际深度（负值，0 为海面）
- $\zeta$ — 自由海面高度 (zeta)
- $h$ — 局地水深 (bathymetry)
- $h_c = 100\ \text{m}$ — 临界深度
- $\sigma$ — S 坐标值（s_rho 或 s_w）
- $C_s$ — 拉伸曲线（Cs_r 或 Cs_w）

### U/V 点水深

文件不包含 h_u/h_v，从相邻 RHO 点水深平均：

$$h_u(j,i) = \frac{h(j,i) + h(j,i+1)}{2} \qquad h_v(j,i) = \frac{h(j,i) + h(j+1,i)}{2}$$

### 插值方法

- **表层和底层**：直接取顶部/底部 sigma 层原始值（不经插值，与原数据位级一致）
- **中间固定深度层**：线性插值。对每个水平格点，找到夹住目标深度的两个 sigma 层，按权重线性插值
- 水深不足目标深度的格点 → 填充值 (1e37)
- 陆地格点 → 填充值 (1e37)

---

## 输出深度层（15 层）

| 索引 | 深度 | 含义 | 取值方式 |
|:----:|------|------|----------|
| 0 | 0 m | 表层 (surface) | 顶部 sigma 层原始值 |
| 1 | 20 m | 固定深度 | 线性插值 |
| 2 | 40 m | 固定深度 | 线性插值 |
| 3 | 60 m | 固定深度 | 线性插值 |
| 4 | 80 m | 固定深度 | 线性插值 |
| 5 | 100 m | 固定深度 | 线性插值 |
| 6 | 120 m | 固定深度 | 线性插值 |
| 7 | 140 m | 固定深度 | 线性插值 |
| 8 | 160 m | 固定深度 | 线性插值 |
| 9 | 200 m | 固定深度 | 线性插值 |
| 10 | 250 m | 固定深度 | 线性插值 |
| 11 | 300 m | 固定深度 | 线性插值 |
| 12 | 350 m | 固定深度 | 线性插值 |
| 13 | 400 m | 固定深度 | 线性插值 |
| 14 | -99999 | 底层 (bottom) | 底部 sigma 层原始值 |

> **注意**：底层 (索引 14) 的深度坐标值为 -99999（标记值），实际深度随地形变化，在各水平格点上 = 局地水深 + 海面高度。

---

## 输出文件变量

输出文件包含 **17 个变量**：经过深度插值处理的 5 个三维物理量 + 6 个经纬度坐标 + 3 个陆地掩码 + 时间/深度坐标。

### 三维物理变量（含 depth 维度）

| 变量名 | 维度 | 单位 | 说明 |
|--------|------|------|------|
| `temp` | (ocean_time, depth, eta_rho, xi_rho) | Celsius | 位温 |
| `salt` | (ocean_time, depth, eta_rho, xi_rho) | — | 实用盐度 |
| `u` | (ocean_time, depth, eta_u, xi_u) | m·s⁻¹ | x 方向流速分量 |
| `v` | (ocean_time, depth, eta_v, xi_v) | m·s⁻¹ | y 方向流速分量 |
| `w` | (ocean_time, depth, eta_rho, xi_rho) | m·s⁻¹ | 垂直速度 |

### 地理坐标变量（用于空间定位，从原始文件复制）

| 变量名 | 维度 | 单位 | 对应物理变量 |
|--------|------|------|-------------|
| `lon_rho`, `lat_rho` | (eta_rho, xi_rho) | degree | temp, salt, w |
| `lon_u`, `lat_u` | (eta_u, xi_u) | degree | u |
| `lon_v`, `lat_v` | (eta_v, xi_v) | degree | v |

### 陆地掩码变量

| 变量名 | 维度 | 说明 |
|--------|------|------|
| `mask_rho` | (eta_rho, xi_rho) | RHO 点掩码 (0=陆地, 1=水域) |
| `mask_u` | (eta_u, xi_u) | U 点掩码 |
| `mask_v` | (eta_v, xi_v) | V 点掩码 |

### 坐标变量

| 变量名 | 维度 | 说明 |
|--------|------|------|
| `ocean_time` | (ocean_time) | 平均时间 (seconds since 2014-01-01) |
| `depth` | (depth) | 目标深度层 (meter) |

### 不包含的变量（请从原始文件获取）

以下变量**未包含**在输出文件中：

- **二维时变场**：`zeta`, `zeta_detided`, `ubar`, `vbar`
- **静态网格场**：`h`, `f`, `pm`, `pn`, `lon_psi`, `lat_psi`, `mask_psi`
- **垂向参考**：`s_rho`, `s_w`, `Cs_r`, `Cs_w`
- **模型参数**：所有标量参数 (dt, rho0, Vtransform, ...)

> 需要地形、海面高度、或 PSI 点坐标时，请打开原始文件 `E:\ROMS\daily\2023\roms_avg_YYYYMMDDZ12.nc`。

---

## 文件格式

| 属性 | 值 |
|------|-----|
| **格式** | NetCDF-3, 64-bit offset |
| **填充值** | 1.0 × 10³⁷ |
| **精度** | float32（lon/lat/mask 为 float64） |
| **维度** | 8 个 (ocean_time, depth, eta_rho, xi_rho, eta_u, xi_u, eta_v, xi_v) |
| **变量数** | 17 个 |
| **输出文件大小** | ~1.4 GB/文件（原始 3.8 GB 的 36%） |

---

## 使用示例

### Python (netCDF4)

```python
import netCDF4 as nc

ds = nc.Dataset('roms_avg_20230101Z12.nc', 'r')

# 海面温度 (depth index 0 = surface)
sst = ds.variables['temp'][0, 0, :, :]  # (eta_rho, xi_rho)

# 200m 深度温度 (depth index 9)
temp_200m = ds.variables['temp'][0, 9, :, :]

# 底层温度 (depth index 14)
temp_bottom = ds.variables['temp'][0, 14, :, :]

# 深度坐标（-99999 = 底层标记）
depth_levels = ds.variables['depth'][:]

# 经纬度和掩码（已包含在文件中）
lon = ds.variables['lon_rho'][:]
lat = ds.variables['lat_rho'][:]
mask = ds.variables['mask_rho'][:]

# 绘制海面温度空间图
import matplotlib.pyplot as plt
import numpy as np
sst_masked = np.where(mask == 1, sst, np.nan)
plt.pcolormesh(lon, lat, sst_masked, cmap='Spectral_r')
plt.colorbar(label='SST (°C)')
plt.title('South China Sea SST — 2023-01-01')

ds.close()
```

### Python (xarray)

```python
import xarray as xr

ds = xr.open_dataset('roms_avg_20230101Z12.nc')

# 沿深度维切片 — 某个格点的全深度剖面
profile = ds.temp.isel(ocean_time=0, eta_rho=500, xi_rho=1000)
print(profile.values)  # (15,) — 15 个深度的水温剖面
```

### 命令行

```bash
ncdump -h roms_avg_20230101Z12.nc        # 查看元数据
ncdump -v depth roms_avg_20230101Z12.nc  # 查看深度坐标
```

---

## 注意事项

1. **底层深度是变化的**：底层在各格点的实际深度 = 局地水深 + 海面高度，`depth` 坐标中的 `-99999` 仅是标记值。
2. **浅水区掩码**：当目标深度超过局地水深时（如在水深 50m 处提取 200m 水温），对应值为 FillValue (1e37)。
3. **U/V 网格偏移**：`u` 和 `v` 分别使用 U 点和 V 点水平网格，与 `temp`/`salt` 的 RHO 网格有半格点偏移。
4. **W 的垂向位置**：`w` 使用 46 层 W 点（层界面），`temp`/`salt`/`u`/`v` 使用 45 层 RHO 点（层中心）。
5. **无地形/海面高度信息**：输出文件不含 `h` (bathymetry) 和 `zeta` (sea surface height)，需从原始文件读取。
6. **时间平均**：原始为日平均 (`cell_methods = "ocean_time: mean"`)，插值后保留此语义。

---

## 处理脚本用法

```bash
python D:/ROMS/daily/depth_process/depth_interp.py

# 指定日期范围
python depth_interp.py --start-date 20230101 --end-date 20230131

# 预览文件列表（不实际处理）
python depth_interp.py --dry-run

# 覆盖已有输出
python depth_interp.py --overwrite

# 查看所有选项
python depth_interp.py --help
```

### 预估资源消耗

| 项目 | 值 |
|------|-----|
| 单文件处理时间 | ~2.5 分钟 |
| 365 文件总时间 | ~15 小时 |
| 单文件输出大小 | ~1.4 GB |
| 365 文件总输出 | ~500 GB |
| 内存占用 | ~2 GB |

---

## 版本信息

- **ROMS 版本**: 4.2 (git: 5a15936c)
- **处理脚本**: `depth_interp.py`
- **生成时间**: 2026-07-27
- **插值算法**: 向量化线性插值 (numpy)
