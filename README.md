# 麦麦轻食周计划 · McFit Week

> 输入身高体重和目标，基于麦当劳**真实菜单与官方营养数据**，一键生成一周三餐计划，
> 联动官方算价，输出一份可分享的可视化报告。

麦当劳程序员节创意开发大赛（1024）参赛作品 · 纯 Python · 仅标准库 · MIT

[演示报告（HTML）](docs/samples/demo-report.html) · [MCP 接入说明](MCP_INTEGRATION.md) · [参赛声明](CONTEST_DECLARATION.md)

## 它解决什么问题

市面上查单个汉堡热量的工具很多，但没有人回答这个问题：

> **"我想减脂，这一周在麦当劳怎么吃？"**

麦麦轻食周计划把这个问题拆成一条完整闭环：

```
身体数据 → 每日营养目标 → 一周三餐组合 → 官方算价 → 可分享的周计划报告
```

全部基于麦当劳中国 MCP 的**真实数据**：约 160 项餐品官方营养表、
当前门店在售菜单与现价、可用优惠券、官方算价接口。

## 功能特性

- **真实数据驱动**：营养数据、菜单、价格全部来自麦当劳 MCP 实时接口，不是写死的表格
- **周维度规划**：不是"这一餐吃什么"，而是 7 天 × 3 餐的组合搜索，
  热量误差控制在 ±3% 以内，蛋白目标达成率 7/7（演示场景）
- **智能组合搜索**：随机采样 + 局部置换优化，打分函数综合考虑
  宏量偏差、钠上限、蛋白密度、价格与多样性（同款不重复、最近两天不重样）
- **官方算价核对**：计划价格走 `calculate-price` 接口，不自己拍脑袋
- **热量直观化**：每处 kcal 后附「约等于几个苹果」换算（1 个中等苹果 ≈ 95 kcal），
  一眼看出热量量级
- **优惠券攻略**：联动 `available-coupons` / `query-my-coupons` / `query-store-coupons`，
  按天标注本周计划里"哪天哪些餐品有券"，并说明麦当劳 App / 微信小程序的领券入口
- **诚实降级**：预算不够或菜单达不到目标时，明确告知差距，不虚报、不硬塞
- **自包含报告**：单个 HTML 文件，无外部依赖，手机可直接打开，方便晒图
- **演示模式**：`--demo` 使用内置接口快照数据，无需 Token 即可完整体验

## 快速开始

环境要求：Python 3.10+，无第三方依赖。

```bash
git clone https://github.com/<your-name>/mcd-fit-week.git
cd mcd-fit-week

# 演示模式：无需 Token，三行命令出报告
PYTHONPATH=src python3 -m mcdfitweek \
  --height 175 --weight 70 --age 28 --gender male \
  --goal cut --demo -o report.html
```

打开 `report.html` 即可看到一周计划。示例输出见
[docs/samples/demo-report.html](docs/samples/demo-report.html)。

## 实时模式（接入麦当劳 MCP）

1. 到[麦当劳 MCP 开放平台](https://open.mcd.cn/mcp)用手机号登录，
   控制台点击「激活」申请 MCP Token（免费）
2. 设置环境变量并运行：

```bash
export MCD_MCP_TOKEN="你的Token"

PYTHONPATH=src python3 -m mcdfitweek \
  --height 175 --weight 70 --age 28 --gender male \
  --activity moderate --goal cut --budget 700 --city 上海市
```

实时模式会拉取官方营养表、附近门店菜单与现价，并用 `calculate-price` 核对每日价格。

## 使用示例

```bash
# 女性均衡饮食，有预算约束
python3 -m mcdfitweek --height 160 --weight 55 --age 26 --gender female \
  --activity light --goal maintain --budget 500

# 增肌，排除忌口
python3 -m mcdfitweek --height 180 --weight 80 --age 30 --gender male \
  --activity active --goal bulk --exclude "可乐,雪碧"

# 复现同一计划（固定随机种子）
python3 -m mcdfitweek --height 175 --weight 70 --age 28 --gender male \
  --goal cut --seed 42
```

主要参数：`--goal cut|maintain|bulk`（减脂/均衡/增肌）、
`--activity sedentary|light|moderate|active`、`--budget`（周预算，元）、
`--exclude`（忌口，逗号分隔）、`--days`（规划天数）、`--seed`（随机种子）。

## 工作原理

| 阶段 | 说明 |
| --- | --- |
| 目标计算 | Mifflin-St Jeor 公式算 BMR，按活动系数得 TDEE，目标调整（减脂 −20% / 均衡 / 增肌 +15%），蛋白 1.6–1.8 g/kg |
| 数据对齐 | 菜单营销名（三件套/大杯…）与营养表标准名归一化模糊匹配；未匹配价格按热量就近估算 |
| 组合搜索 | 每餐按热量配额（早30/午40/晚30%）搜索「主餐+小食+饮品」；高蛋白目标允许双主餐；320 次随机采样 + 局部置换优化 |
| 打分函数 | 热量偏差 ×2.0、蛋白偏差 ×3.0、脂肪 ×0.6、碳水 ×0.4，叠加钠软上限、蛋白密度奖励、价格惩罚、多样性惩罚 |
| 算价核对 | 实时模式逐日调用 `calculate-price`，输出周总价并与预算对比 |
| 报告渲染 | 自包含 HTML：目标卡、每日进度条、餐单明细、周汇总、超预算提醒 |

已知限制：极高热量目标（如增肌期 3500+ kcal/日）受菜单丰度限制可能只能达成
80–90%，报告会如实展示差距而非虚报——这正是"诚实降级"的设计选择。

## 项目结构

```
mcd-fit-week/
├── src/mcdfitweek/
│   ├── mcp_client.py    # MCP 客户端（Streamable HTTP，无状态协议）
│   ├── nutrition.py     # 营养表解析、名称对齐、BMR/TDEE 目标计算
│   ├── planner.py       # 一周三餐组合搜索算法
│   ├── report.py        # 自包含 HTML 报告渲染
│   └── cli.py           # 命令行入口
├── data/                # 演示数据（MCP 返回快照转换）
├── docs/samples/        # 接口原始返回快照 + 演示报告
├── scripts/             # 演示数据构建脚本
└── tests/               # 单元测试
```

## 开发

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
```

## 数据来源与免责声明

营养与菜单数据来自麦当劳中国 MCP 服务（`https://mcp.mcd.cn`）；
`docs/samples/` 与 `data/` 中的演示数据为接口返回快照，仅供离线演示。
本项目为非官方参赛作品，输出仅供参考，不构成医疗或营养专业建议；
餐品信息、价格及供应情况以麦当劳官方渠道实时结果为准。

## 致谢

- [麦当劳中国 MCP Server](https://github.com/M-China/mcd-mcp-server) 提供开放接口
- [WorkBuddy](https://www.workbuddy.cn) 作为官方合作伙伴提供开发环境
