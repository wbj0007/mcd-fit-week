"""营养数据模型与每日目标计算。

数据来源：麦当劳中国 MCP `list-nutrition-foods` 工具（约 160 项官方营养数据）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 活动系数与目标调整（常用运动营养学经验值）
ACTIVITY_FACTORS = {
    "sedentary": 1.2,    # 久坐办公
    "light": 1.375,      # 每周轻运动 1-3 次
    "moderate": 1.55,    # 每周运动 3-5 次
    "active": 1.725,     # 每周运动 6-7 次
}
GOAL_LABELS = {"cut": "减脂", "maintain": "均衡", "bulk": "增肌"}
GOAL_KCAL_FACTOR = {"cut": 0.80, "maintain": 1.00, "bulk": 1.15}
PROTEIN_G_PER_KG = {"cut": 1.6, "maintain": 1.4, "bulk": 1.8}
FAT_KCAL_RATIO = {"cut": 0.28, "maintain": 0.27, "bulk": 0.25}
SODIUM_CAP_MG = 2000.0  # 每日钠建议上限
APPLE_KCAL = 95.0  # 一个中等苹果（约 182 g 可食部）≈ 95 kcal


def apples_equivalent(kcal: float) -> str:
    """把热量换算成「约等于几个苹果」的直观描述。

    换算基准：1 个中等苹果 ≈ 95 kcal（USDA medium apple，约 182 g 可食部）。
    """
    if kcal <= 0:
        return "0 个苹果"
    n = kcal / APPLE_KCAL
    if n < 0.5:
        return "不到半个苹果"
    if n < 1.5:
        return "约 1 个苹果"
    return f"约 {round(n)} 个苹果"


@dataclass
class Food:
    """一份餐品的营养与价格信息。"""

    name: str
    kcal: float
    protein: float
    fat: float
    carb: float
    sodium: float = 0.0
    calcium: float = 0.0
    price: float | None = None
    kind: str = ""  # main / breakfast / side / drink，由 planner 填充

    def scaled(self, qty: float) -> "Food":
        return Food(
            name=self.name,
            kcal=self.kcal * qty,
            protein=self.protein * qty,
            fat=self.fat * qty,
            carb=self.carb * qty,
            sodium=self.sodium * qty,
            calcium=self.calcium * qty,
            price=None if self.price is None else self.price * qty,
            kind=self.kind,
        )


@dataclass
class DailyTarget:
    """每日营养目标。"""

    kcal: float
    protein: float
    fat: float
    carb: float
    sodium_cap: float = SODIUM_CAP_MG


def parse_nutrition_table(raw: str) -> list[Food]:
    """解析 `list-nutrition-foods` 返回的 data 字符串。

    形如::

        [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
          巨无霸,null,2146,513,27,26,42,961,171
          ...

    注意：描述列可能含逗号，而数值列固定 7 个，因此从右侧切分；
    同名餐品去重（接口存在重复行）。
    """
    text = (raw or "").strip()
    head = re.match(r"^\[\d+\]\{[^}]*\}:", text)
    if head:
        text = text[head.end():]
    foods: list[Food] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        name, nums = parts[0], parts[-7:]
        try:
            _kj, kcal, protein, fat, carb, sodium, calcium = (float(x) for x in nums)
        except ValueError:
            continue
        if not name or name in seen:
            continue
        seen.add(name)
        foods.append(
            Food(name=name, kcal=kcal, protein=protein, fat=fat, carb=carb,
                 sodium=sodium, calcium=calcium)
        )
    return foods


# 菜单营销名 -> 营养表名 对齐时要剥落的套餐后缀
_NAME_SUFFIXES = ("三件套", "四件套", "两件套", "单品精选", "开心乐园餐", "套餐", "随心选")


def normalize_name(name: str) -> str:
    """菜单名与营养表名对齐：统一全角括号、去空格、剥落套餐后缀。"""
    s = (name or "").replace("（", "(").replace("）", ")").replace("™", "")
    s = s.replace(" ", "").replace('"', "").replace("“", "").replace("”", "")
    for suf in _NAME_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    return s


# 规格词：菜单名与营养表名互转时互相剥落
_SPEC_WORDS = ("大杯", "中杯", "小杯", "盒装", "迷你", "经典", "原味", "麦咖啡")


def align_menu_prices(foods: list["Food"], menu_items: list[dict]) -> int:
    """把菜单价格对齐到营养表餐品（按归一化名称模糊匹配）。

    菜单是营销名（如「麦辣鸡腿汉堡三件套」「大杯鲜萃咖啡」），营养表是标准名
    （如「麦辣鸡腿汉堡」「鲜萃咖啡」）。匹配顺序：精确 -> 剥规格词 -> 互相包含。
    返回成功匹配的餐品数量。
    """
    price_by_norm: dict[str, float] = {}
    orig_by_norm: dict[str, str] = {}
    for item in menu_items:
        orig = item.get("name", "") or ""
        try:
            price = float(item.get("price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or not orig:
            continue
        norm = normalize_name(orig)
        # 同一归一化键出现多次时（如「巨无霸」与「巨无霸三件套」），
        # 保留原名更短的条目——那才是单品价格
        if norm not in price_by_norm or len(orig) < len(orig_by_norm[norm]):
            price_by_norm[norm] = price
            orig_by_norm[norm] = orig

    matched = 0
    for food in foods:
        if food.price is not None:
            continue
        norm = normalize_name(food.name)
        price = price_by_norm.get(norm)
        if price is None:
            for spec in _SPEC_WORDS:
                price = price_by_norm.get(norm.replace(spec, ""))
                if price is not None:
                    break
        if price is None:
            for key, value in price_by_norm.items():
                if len(key) >= 2 and (norm.endswith(key) or key.endswith(norm)
                                      or key in norm or norm in key):
                    price = value
                    break
        if price is not None:
            food.price = price
            matched += 1

    # 未匹配到菜单价格的餐品做中位数估算（按热量就近），
    # 否则无价格餐品在规划打分中等同于免费，会扭曲预算约束
    priced = [f for f in foods if f.price is not None]
    if priced:
        fallback = sorted(f.price for f in priced)[len(priced) // 2]
        for food in foods:
            if food.price is not None:
                continue
            neighbours = [f.price for f in priced if abs(f.kcal - food.kcal) <= 120]
            food.price = (sorted(neighbours)[len(neighbours) // 2]
                          if neighbours else fallback)
    return matched


def bmr_mifflin(gender: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Mifflin-St Jeor 基础代谢率公式。"""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if gender == "male" else base - 161


def daily_target(
    gender: str,
    weight_kg: float,
    height_cm: float,
    age: int,
    activity: str = "moderate",
    goal: str = "cut",
) -> DailyTarget:
    """由身体数据推算每日热量与三大宏量目标。"""
    if activity not in ACTIVITY_FACTORS:
        raise ValueError(f"未知活动量: {activity}")
    if goal not in GOAL_KCAL_FACTOR:
        raise ValueError(f"未知目标: {goal}")
    tdee = bmr_mifflin(gender, weight_kg, height_cm, age) * ACTIVITY_FACTORS[activity]
    kcal = tdee * GOAL_KCAL_FACTOR[goal]
    protein = PROTEIN_G_PER_KG[goal] * weight_kg
    fat = kcal * FAT_KCAL_RATIO[goal] / 9  # 脂肪 9 kcal/g
    carb = max(0.0, (kcal - protein * 4 - fat * 9) / 4)  # 蛋白/碳水 4 kcal/g
    return DailyTarget(
        kcal=round(kcal),
        protein=round(protein),
        fat=round(fat),
        carb=round(carb),
    )
