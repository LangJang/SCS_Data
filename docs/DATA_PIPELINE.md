# SCS Marine Data Tool — 数据链路说明

> 版本: 2026-07-30 | 作者: Wang Shuo

本文档详细说明 SCS Marine Data Tool 的数据链路架构：数据文件在磁盘上的组织方式、配置系统如何定位文件、适配器如何识别数据源并映射变量，以及新设备迁移的完整步骤。

---

## 目录

1. [项目文件结构](#1-项目文件结构)
2. [数据文件组织](#2-数据文件组织)
3. [配置系统：链接的构造方式](#3-配置系统链接的构造方式)
4. [适配器层：数据源识别与变量映射](#4-适配器层数据源识别与变量映射)
5. [数据加载链路（完整流程）](#5-数据加载链路完整流程)
6. [Git 版本控制范围](#6-git-版本控制范围)
7. [新设备迁移步骤](#7-新设备迁移步骤)

---

## 1. 项目文件结构

```
SCS_data/                           ← Git 仓库根目录
├── .git/                           ← Git 版本控制
├── .gitignore                      ← 忽略规则
├── .claude/                        ← Claude Code 项目配置
├── .vscode/                        ← VS Code 工作区配置
├── CLAUDE.md                       ← 项目文档（供 AI 阅读）
│
├── config.yaml                     ★ 数据集注册表 — 核心配置文件
│
├── src/
│   ├── main.py                     ← GUI 入口（PyQt6，开发中）
│   ├── core/
│   │   ├── config.py               ★ 路径常量定义
│   │   ├── config_reader.py        ★ 解析 config.yaml
│   │   ├── canonical.py            ★ 规范变量/坐标 Schema
│   │   ├── nc_reader.py            ← 文件扫描、加载、数据源检测
│   │   ├── time_assembler.py       ← ROMS 多文件时间序列合并
│   │   ├── roms_utils.py           ← 字段提取、插值
│   │   ├── aligner.py              ← ROMS ↔ CMEMS 时空对齐
│   │   ├── pipeline.py             ← 高层编排器
│   │   ├── preprocess.py           ← 缺失值/重采样/裁剪
│   │   ├── export.py               ← CSV / Excel / NetCDF 导出
│   │   ├── fishery_raster.py       ← 渔业栅格分析
│   │   └── adapters/
│   │       ├── __init__.py         ★ 适配器注册表
│   │       ├── base.py             ← DataSourceAdapter 抽象基类
│   │       ├── roms_adapter.py     ← 原始 ROMS（sigma 坐标）
│   │       ├── standard_roms_adapter.py ← 标准化 ROMS（depth 坐标）
│   │       ├── rectilinear_roms_adapter.py ← 矩形网格 ROMS
│   │       └── cmems_adapter.py    ← CMEMS / Copernicus
│   ├── viz/
│   │   ├── map_plotter.py          ← Cartopy 地图渲染
│   │   └── time_plotter.py         ← 时间序列图
│   └── ui/                         ← PyQt6 GUI（开发中）
│
├── tools/
│   ├── check_env.py                ← 环境验证
│   ├── compare_sources.py          ← ROMS/CMEMS 跨源对比
│   ├── interp_to_005deg.py         ← 0.25° → 0.05° 插值
│   ├── merge_depth_layers.py       ← 深度层合并
│   └── regrid_roms_to_rectilinear.py ← ROMS 曲线→矩形网格
│
├── run_roms_demo.py                ← ROMS 演示入口
├── run_cmes_demo.py                ← CMEMS 演示入口
├── environment.yml                 ← Conda 环境定义
├── requirements.txt                ← Pip 依赖清单
│
├── data/                           ← [git-ignored] 本地数据
├── output/                         ← [git-ignored] 生成产物
└── docs/                           ← 文档
```

> ★ = 核心配置/架构文件，理解数据链路的关键入口。

---

## 2. 数据文件组织

数据文件分布在 **两个根目录** 下，总计约 **180 GB**。

### 2.1 位置 A：项目 data/ 目录

```
{PROJECT_ROOT}/data/                   ← git-ignored，不在版本控制中
│
├── roms_avg_20230101Z12.nc            ← ROMS 日平均，4.1 GB/个
├── roms_avg_20230102Z12.nc
├── roms_avg_20230103Z12.nc
├── ...（共 27 个文件，日期不连续，1 月 18-21 日缺失）
├── roms_avg_20230131Z12.nc
│
├── beibu_fishery_sample.csv           ← 北部湾渔业调查（86 站）
├── northern_scs_fishery.csv           ← 南海北部渔业（95 站）
├── nansha_fishery.csv                 ← 南沙群岛渔业（65 站）
├── xisha_fishery.csv                  ← 西沙群岛渔业（45 站）
└── tuna_202606.xlsx                   ← 金枪鱼生物学调查（SCS-01 站）
```

### 2.2 位置 B：CMEMS 下载目录

```
D:\ChatWithAI\Downloading_CEMES\       ← 独立于项目的外部目录
│
├── SCS_BGC_2020-2022.nc              (35.8 GB)  原始 CMEMS 多变量合并
├── SCS_BGC_DO_CHL_2025.nc            (13.6 GB)  溶解氧 + 叶绿素
├── SCS_BGC_PH_2023-2025.nc           (4.5 GB)   pH
├── SCS_BGC_no3_po4_si_2023-2025.nc   (20.4 GB)  硝酸盐 + 磷酸盐 + 硅酸盐
│
├── output/                            ← 标准化处理产物
│   ├── SCS_cmems_do_chl.nc           (6.0 GB)   0.05°, 14 层, DO+Chl
│   ├── SCS_cmems_no3_po4_si.nc       (10.4 GB)  0.05°, 14 层, 营养盐
│   ├── SCS_cmems_ph.nc               (2.6 GB)   0.05°, 14 层, pH
│   ├── SCS_bottom_cmems.nc           (4.4 GB)   底层专用提取
│   └── roms/
│       ├── roms_avg_20230101Z12.nc    (1.5 GB)   标准化的 ROMS
│       ├── ...（27 个文件）
│       └── roms_rectilinear_005deg.nc (1.5 GB)   ROMS 矩形网格重投影
│
├── downloader.py                     ← CMEMS 下载脚本
├── case_01_process_roms.py           ← ROMS 标准化处理脚本
├── 02_process_cmems.py               ← CMEMS 标准化处理脚本
└── compress_cmems.py                 ← CMEMS 压缩脚本
```

### 2.3 数据层级总览

```
┌─────────────────────────────────────────────────────────┐
│  层级 0: 下载脚本                                        │
│  downloader.py  →  CMEMS FTP/API  →  原始 NetCDF 文件     │
├─────────────────────────────────────────────────────────┤
│  层级 1: 原始数据  (~180 GB，git-ignored)                 │
│  ROMS daily x27  (data/)                                │
│  CMEMS 4 文件    (Downloading_CEMES/)                    │
├─────────────────────────────────────────────────────────┤
│  层级 2: 标准化产物  (~22 GB，git-ignored)                │
│  统一 0.05°, 14 层 (0-400 m), 规范变量名                  │
│  Downloading_CEMES/output/                               │
├─────────────────────────────────────────────────────────┤
│  层级 3: 辅助数据  (~1 MB，git-ignored)                   │
│  渔业 CSV、生物学站 Excel                                 │
│  data/*.csv, data/*.xlsx                                │
├─────────────────────────────────────────────────────────┤
│  层级 4: 可视化输出  (git-ignored)                        │
│  output/ — PNG 地图、时间序列图                           │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 配置系统：链接的构造方式

数据链路由 **两个文件** 协作完成：

### 3.1 `src/core/config.py` — 路径常量

```python
# 项目根目录（自动推导）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# __file__ = src/core/config.py
# → PROJECT_ROOT = D:\ChatWithAI\SCS_data

# CMEMS 数据目录（硬编码绝对路径 ⚠️）
DATA_DIR_CMEMS = Path("D:/ChatWithAI/Downloading_CEMES")

# ROMS 数据目录（相对路径，相对于 PROJECT_ROOT ✓）
DATA_DIR_ROMS = PROJECT_ROOT / "data"        # → D:\ChatWithAI\SCS_data\data\

# 旧版 ROMS 目录（硬编码绝对路径 ⚠️）
DATA_DIR_ROMS_LEGACY = Path("D:/ChatWithAI")

# 输出目录（相对路径 ✓）
OUTPUT_DIR = PROJECT_ROOT / "output"

# 快速查找表
SOURCE_DIRS = {
    "ROMS":  DATA_DIR_ROMS,      # D:\ChatWithAI\SCS_data\data\
    "CMEMS": DATA_DIR_CMEMS,     # D:\ChatWithAI\Downloading_CEMES\
}
```

### 3.2 `config.yaml` — 数据集注册表

每个数据集条目指定 `path` + `file_pattern`，组合后定位实际文件：

```yaml
datasets:
  - name: "SCSIO Standardized (0–400 m, 0.05°)"
    source: "SCSIO-Standard"
    # path 为目录，file_pattern 为 glob 匹配
    path: "D:/ChatWithAI/Downloading_CEMES/output/roms/"     # ⚠️ 绝对路径
    file_pattern: "roms_avg_*.nc"
    variables: [temperature, salinity, u_current, v_current, w_velocity]
    vertical:
      type: depth
      layers: 14
      depth_values: [0, 20, 40, 60, 80, 100, 120, 140, 160, 200, 250, 300, 350, 400]

  - name: "SCSIO SCS Daily Average (raw sigma)"
    hidden: true                     # ← 隐藏，GUI 不显示
    source: "SCSIO"
    path: "data/"                    # ✓ 相对路径
    file_pattern: "roms_avg_*.nc"

  - name: "CMEMS Standardized — DO & Chlorophyll (0–400 m, 0.05°)"
    source: "CMEMS"
    path: "D:/ChatWithAI/Downloading_CEMES/output/"           # ⚠️ 绝对路径
    file_pattern: "SCS_cmems_do_chl.nc"

overlays:
  - label: "Beibu Gulf Fishery"
    path: "data/beibu_fishery_sample.csv"                     # ✓ 相对路径
    type: fishery

  - label: "Tuna Survey (SCS-01)"
    path: "D:/ChatWithAI/SCS_data/data/tuna_202606.xlsx"      # ⚠️ 绝对路径
    type: station
```

### 3.3 路径解析逻辑

由 `config_reader.py` 中的 `DatasetConfig.resolve_path()` 实现：

```python
def resolve_path(self, base_dir: Path) -> Path:
    p = Path(self.path)
    if p.is_absolute():
        return p          # D:/... 直接返回，不转换
    return (base_dir / p).resolve()  # 相对路径拼接到 config.yaml 所在目录
```

### 3.4 硬编码绝对路径清单（⚠️ 迁移障碍）

| 文件 | 行号 | 硬编码路径 | 影响 |
|------|------|-----------|------|
| `src/core/config.py` | L20 | `D:/ChatWithAI/Downloading_CEMES` | CMEMS 数据源目录 |
| `src/core/config.py` | L30 | `D:/ChatWithAI` | ROMS 旧版目录 |
| `config.yaml` | L43, L76 | `D:/ChatWithAI/Downloading_CEMES/output/roms/` | 标准化 ROMS 数据集 |
| `config.yaml` | L108, L139, L166 | `D:/ChatWithAI/Downloading_CEMES/output/` | 标准化 CMEMS 数据集 |
| `config.yaml` | L241, L272, L299 | `D:/ChatWithAI/Downloading_CEMES/` | 原始 CMEMS 数据集（隐藏） |
| `config.yaml` | L382 | `D:/ChatWithAI/SCS_data/data/tuna_202606.xlsx` | 金枪鱼生物学站 |

---

## 4. 适配器层：数据源识别与变量映射

### 4.1 适配器注册与优先级

`src/core/adapters/__init__.py` 中定义：

```python
REGISTERED_ADAPTERS = [
    StandardROMSAdapter,      # 优先级 1（最优先）
    ROMSAdapter,               # 优先级 2
    RectilinearROMSAdapter,    # 优先级 3
    CMEMSAdapter,              # 优先级 4（兜底）
]
```

`detect_source(dataset, file_path)` 按顺序调用每个适配器的 `detect()` 类方法，返回第一个匹配。

### 4.2 四个适配器的检测规则

| 适配器 | source_name | 检测条件 |
|--------|-------------|---------|
| **StandardROMSAdapter** | `SCSIO-Standard` | 有 `ocean_time` + `lon_rho` + `depth`，且 **没有** `s_rho` |
| **ROMSAdapter** | `SCSIO` | 有 `ocean_time` + `s_rho` + `lon_rho`（原始 sigma 坐标） |
| **RectilinearROMSAdapter** | `SCSIO-Rectilinear` | 有 1-D `longitude` + `latitude` + `depth` + ROMS 变量名（`temp`/`salt`/`u`/`v`/`w`），且没有 `ocean_time` |
| **CMEMSAdapter** | `CMEMS` | 有 CF 标准坐标（`time` + `longitude`/`lat`/`lon` + `latitude`/`lat`），且没有 `ocean_time`；或文件名以 `cmems_` 开头 |

### 4.3 适配器输出：SourceMeta

每个适配器的 `adapt(ds)` 方法返回统一的数据结构：

```python
@dataclass
class SourceMeta:
    source_name:    str              # "SCSIO" | "SCSIO-Standard" | "SCSIO-Rectilinear" | "CMEMS"
    grid_type:      GridType         # RECTILINEAR | CURVILINEAR
    vertical_type:  VerticalType     # DEPTH | SIGMA | NONE
    var_map:        dict             # {canonical_name: source_native_name}
    coord_map:      dict             # {canonical_coord: source_native_coord}
    time_dim:       str              # 时间维度名称
    extra_attrs:    dict             # 其他元数据
```

### 4.4 变量映射示例

| 规范名称 (canonical) | ROMS (SCSIO) | Standard ROMS | CMEMS |
|----------------------|-------------|--------------|-------|
| `temperature` | `temp` | `temp` | `thetao` |
| `salinity` | `salt` | `salt` | `so` |
| `u_current` | `u` | `u` | `uo` |
| `v_current` | `v` | `v` | `vo` |
| `w_velocity` | `w` | `w` | `wo` |
| `chlorophyll` | — | — | `chl` |
| `dissolved_oxygen` | — | — | `o2` |
| `nitrate` | — | — | `no3` |
| `phosphate` | — | — | `po4` |
| `silicate` | — | — | `si` |
| `ph` | — | — | `ph` |

### 4.5 网格类型差异

```
CURVILINEAR (ROMS)              RECTILINEAR (CMEMS / Standardized)
┌─────────────────┐              ┌─────────────────┐
│ ╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲  │              │ ┌─┬─┬─┬─┬─┬─┐  │
│ ╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲  │              │ ├─┼─┼─┼─┼─┼─┤  │
│ ╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲  │              │ ├─┼─┼─┼─┼─┼─┤  │
│ ╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱  │              │ ├─┼─┼─┼─┼─┼─┤  │
└─────────────────┘              └─────────────────┘
 2-D lon/lat                      1-D lon + 1-D lat
 每个点有唯一坐标                    规则网格，坐标可广播
```

ROMS 使用 Arakawa-C 交错网格（ρ, u, v 点各有一组坐标），适配器将 ρ 点坐标映射为规范坐标，其他格点存入 `extra_attrs["staggered_coords"]`。

---

## 5. 数据加载链路（完整流程）

### 5.1 ROMS 数据流（`run_roms_demo.py`）

```
config.py                          config.yaml
    │                                    │
    ▼                                    ▼
DATA_DIR_ROMS                      file_pattern
= PROJECT_ROOT / "data"            = "roms_avg_*.nc"
    │                                    │
    └──────────┬─────────────────────────┘
               ▼
       TimeAssembler(data_dir)
               │
       .scan("roms_avg_*.nc")
               │
    ┌──────────┴──────────┐
    │ glob 匹配文件         │
    │ 解析文件名中的日期     │
    │ 排序，检测缺失日期    │
    │ 构建 _file_map       │
    └──────────┬──────────┘
               ▼
       .assemble()
               │
    ┌──────────┴──────────┐
    │ xr.open_mfdataset() │  ← 懒加载（dask），105 GB 不入内存
    │ chunks={"ocean_time": 1}│
    │ compat="override"    │
    └──────────┬──────────┘
               ▼
       detect_source(first_file_ds)
               │
    ┌──────────┴──────────┐
    │ 遍历 REGISTERED_ADAPTERS │
    │ 找到 ROMSAdapter.MATCH │
    │ → adapt(ds) → SourceMeta │
    └──────────┬──────────┘
               ▼
       AssembledMeta(
           source_meta = SourceMeta,
           time_labels = [...],
           missing_indices = [17,18,19,20]
       )
               │
               ▼
       extract_field(assembled_ds, meta, var, time_idx, level_idx)
               │
    ┌──────────┴──────────┐
    │ meta.source_var("temperature") → "temp" │
    │ .isel(ocean_time=i, s_rho=level)        │
    │ 返回 (DataArray, lon, lat)               │
    └──────────┬──────────┘
               ▼
       plot_map(da, lon, lat, title, cmap, output_path)
               │
               ▼
       output/roms_demo/*.png
```

### 5.2 CMEMS 数据流（`run_cmes_demo.py`）

```
config.py                          config.yaml
    │                                    │
    ▼                                    ▼
DATA_DIR_CMEMS                     file_pattern
= "D:/ChatWithAI/Downloading_CEMES" = "SCS_cmems_do_chl.nc"
    │                                    │
    └──────────┬─────────────────────────┘
               ▼
       NCReader(data_dir)
               │
       .scan_files("*.nc")  →  [Path, Path, ...]
               │
       .load(file_path)
               │
    ┌──────────┴──────────┐
    │ xr.open_dataset()    │  ← 单个文件急切加载
    │ detect_source(ds, path) │
    │ → CMEMSAdapter.adapt()  │
    │ → SourceMeta            │
    └──────────┬──────────┘
               ▼
       extract_field(ds, meta, var, time_idx, level_idx)
               │
    ┌──────────┴──────────┐
    │ meta.source_var("dissolved_oxygen") → "o2" │
    │ .isel(time=i, depth=level)                  │
    │ 返回 (DataArray, lon, lat)                   │
    └──────────┬──────────┘
               ▼
       plot_map(da, lon, lat, title, cmap, output_path)
               │
               ▼
       output/cemes_demo/*.png
```

### 5.3 跨源对比数据流（`tools/compare_sources.py`）

```
ROMS (curvilinear)                    CMEMS (rectilinear)
       │                                      │
       ▼                                      ▼
  SourceAligner                        SourceAligner
       │                                      │
       ├── Temporal match ────────────────────┤
       │   ROMS 12:00Z ←→ CMEMS 00:00Z        │
       │   same calendar day, ≤ 24h delta     │
       │                                      │
       ├── Spatial regrid ────────────────────┤
       │   ROMS curvilinear                   │
       │   → cKDTree nearest-neighbor         │
       │   → CMEMS rectilinear grid           │
       │                                      │
       └── Vertical (deferred) ───────────────┘
           ROMS sigma → depth 尚未实现
```

---

## 6. Git 版本控制范围

### 6.1 受版本控制的文件

- 所有 `.py` 源代码
- `config.yaml`（数据集注册表）
- `environment.yml`、`requirements.txt`
- `CLAUDE.md`、`docs/*.md`
- `tools/` 脚本
- `.claude/` Claude Code 配置
- `.gitignore`

### 6.2 不受版本控制的文件（`.gitignore`）

| 规则 | 说明 |
|------|------|
| `data/` | 整个本地数据目录 |
| `output/` | 所有生成产物 |
| `*.nc`, `*.nc4` | 所有 NetCDF 文件（无论位置） |
| `*.hdf5`, `*.h5` | HDF5 文件 |
| `*.ipynb` | Jupyter Notebook |
| `.vscode/` | IDE 配置 |
| `env/`, `.venv/`, `venv/` | 虚拟环境 |
| `logs/` | 日志 |

### 6.3 需要外部传输的数据（~180 GB）

以下数据在不同设备间通过 **外置硬盘 / NAS / FTP** 传输，不走 Git：

- ROMS daily NetCDF × 27 文件（~105 GB）
- CMEMS 原始 NetCDF × 4 文件（~74 GB）
- 标准化产物 NetCDF × 5 文件（~22 GB）
- 渔业 CSV × 4 文件 + 生物学站 Excel × 1（~1 MB）

---

## 7. 新设备迁移步骤

### 7.1 建议的目录结构

将数据从项目目录中分离，使代码可任意放置：

```
{ROOT}\                          ← 根目录（位置任意，如 E:\SCS_Project\）
│
├── code\                        ← Git 仓库
│   └── SCS_data\                ← git clone 产物
│       ├── config.yaml          （改：所有 path 改为相对路径）
│       ├── src/
│       └── ...
│
├── data\                        ← 所有数据集中存放
│   ├── roms_raw\                ← ROMS daily NC 文件
│   ├── cmems_raw\               ← CMEMS 原始 NC 文件
│   ├── standardized\            ← 标准化处理产物
│   │   ├── cmems\
│   │   └── roms\
│   └── overlays\                ← 渔业 CSV / 生物学站 Excel
│
└── output\                      ← 生成图片/CSV
```

### 7.2 操作步骤

**Step 1 — 克隆代码**

```bash
git clone https://github.com/LangJang/SCS_Data.git code/SCS_data
cd code/SCS_data
```

**Step 2 — 创建 Conda 环境**

```bash
conda env create -f environment.yml
conda activate scs_marine
python tools/check_env.py
```

> 如果 conda 构建失败：
> ```bash
> conda create -n scs_marine python=3.11
> conda activate scs_marine
> conda install -c conda-forge cartopy
> pip install -r requirements.txt
> ```

**Step 3 — 拷贝数据文件**

用外置硬盘或网络将旧设备数据复制到新设备：

| 源路径 | 目标路径 |
|--------|---------|
| `D:\ChatWithAI\Downloading_CEMES\*.nc` | `data/cmems_raw/` |
| `D:\ChatWithAI\Downloading_CEMES\output\` | `data/standardized/` |
| `D:\ChatWithAI\SCS_data\data\roms_avg_*.nc` | `data/roms_raw/` |
| `D:\ChatWithAI\SCS_data\data\*.csv` `*.xlsx` | `data/overlays/` |

**Step 4 — 修改路径配置**

将 `src/core/config.py` 和 `config.yaml` 中的硬编码绝对路径改为相对路径：

```python
# config.py 改动
DATA_DIR_CMEMS = PROJECT_ROOT.parent / "data" / "cmems_raw"
DATA_DIR_ROMS  = PROJECT_ROOT.parent / "data" / "roms_raw"
```

```yaml
# config.yaml 改动：所有 path 改为相对路径
path: "../data/standardized/roms/"
path: "../data/standardized/"
path: "../data/overlays/"
```

**Step 5 — 验证**

```bash
python run_roms_demo.py    # 测试 ROMS 数据加载 + 出图
python run_cmes_demo.py    # 测试 CMEMS 数据加载 + 出图
```

---

## 附录 A：文件大小一览

| 文件 | 大小 | 说明 |
|------|------|------|
| `roms_avg_*.nc` × 27（原始） | ~4.1 GB/个 | data/ 目录下 ROMS 日平均 |
| `SCS_BGC_2020-2022.nc` | 35.8 GB | CMEMS 原始多变量 |
| `SCS_BGC_DO_CHL_2025.nc` | 13.6 GB | CMEMS DO + 叶绿素 |
| `SCS_BGC_PH_2023-2025.nc` | 4.5 GB | CMEMS pH |
| `SCS_BGC_no3_po4_si_2023-2025.nc` | 20.4 GB | CMEMS 营养盐 |
| `SCS_cmems_do_chl.nc` | 6.0 GB | 标准化 CMEMS DO/Chl |
| `SCS_cmems_no3_po4_si.nc` | 10.4 GB | 标准化 CMEMS 营养盐 |
| `SCS_cmems_ph.nc` | 2.6 GB | 标准化 CMEMS pH |
| `roms_rectilinear_005deg.nc` | 1.5 GB | ROMS 矩形网格 |
| 渔业 CSV × 4 | ~10 KB/个 | 调查站数据 |
| `tuna_202606.xlsx` | ~50 KB | 生物学测量 |
| **总计** | **~180 GB** | |

## 附录 B：ROMS 时间跨度与缺口

当前 ROMS 数据覆盖：**2023-01-01 至 2023-01-31**

已知缺口：**1 月 18–21 日**（4 天缺失，共 27 个文件而非 31 个）

`TimeAssembler` 会自动检测并标注缺失日期，`time_plotter.py` 在绘图时用空白标记缺口。

## 附录 C：环境依赖完整清单

```
Python 3.11.15

核心数据：
  numpy 2.4.6        pandas 3.0.3         scipy 1.17.1
  xarray 2026.7.0    netcdf4 1.7.4        cftime 1.6.5

可视化：
  matplotlib 3.11.0  cartopy 0.25.0       seaborn 0.13.2
  proj 9.3.1         pyproj 3.6.1         shapely 2.1.2

GUI：
  PyQt6 6.9.1        Qt 6.9.2

导出/打包：
  openpyxl 3.1.5     pyinstaller 6.21.0

数学后端：
  mkl 2025.0.0       intel-openmp 2025.0.0
```
