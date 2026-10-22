"""一周三餐规划算法。

思路：
1. 每日目标热量按 早 30% / 午 40% / 晚 30% 分配到三餐
2. 每餐从真实菜单池中搜索「主餐 + 小食 + 饮品」组合
3. 打分函数 = 宏量偏差 + 钠超标惩罚 + 价格惩罚（预算紧张时自动倾向低价）
4. 随机贪心多次采样取最优，并对最近两天用过的主餐做多样性惩罚
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .nutrition import DailyTarget, Food

# 餐品分类关键词（中文菜单名匹配）
# 饮品/甜口桶：可乐雪碧咖啡茶豆浆牛奶新地雪冰麦咖啡系列等
DRINK_KEYS = (
    "可乐", "雪碧", "咖啡", "美式", "拿铁", "卡布奇诺", "玛奇朵", "茶", "红茶",
    "豆浆", "牛奶", "奶铁", "燕麦奶", "新地", "麦旋风", "冰淇淋", "果汁",
    "苹果汁", "怡泉", "纯悦", "雪冰", "阿芙佳朵", "朱古力", "柠檬", "麦旋酷",
    "拉明顿", "奶冻", "爆珠", "黑巧", "抹茶", "伯爵",
)
BREAKFAST_KEYS = ("麦满分", "粥", "炒双蛋", "脆薯饼", "脆香油条", "营养卷", "香肠")

SLOTS = ("breakfast", "lunch", "dinner")
SLOT_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
SLOT_SHARE = {"breakfast": 0.30, "lunch": 0.40, "dinner": 0.30}

SEARCH_ROUNDS = 320  # 每餐随机采样次数

# 杯型/规格词：判断“同一款饮品”时剥落
_SIZE_WORDS = ("大杯", "中杯", "小杯", "迷你", "盒装")


def _base_name(name: str) -> str:
    """剥落杯型后的基础名，用于同款不同杯型的去重。"""
    s = name
    for w in _SIZE_WORDS:
        s = s.replace(w, "")
    return s


@dataclass
class Meal:
    """一餐：若干餐品组合。"""

    slot: str
    items: list[Food] = field(default_factory=list)

    @property
    def kcal(self) -> float:
        return sum(f.kcal for f in self.items)

    @property
    def protein(self) -> float:
        return sum(f.protein for f in self.items)

    @property
    def price(self) -> float:
        return sum(f.price or 0.0 for f in self.items)


@dataclass
class DayPlan:
    """一天的计划。"""

    label: str  # 例如 10-23 周五
    meals: list[Meal] = field(default_factory=list)

    @property
    def kcal(self) -> float:
        return sum(m.kcal for m in self.meals)

    @property
    def protein(self) -> float:
        return sum(m.protein for m in self.meals)

    @property
    def fat(self) -> float:
        return sum(f.fat for m in self.meals for f in m.items)

    @property
    def carb(self) -> float:
        return sum(f.carb for m in self.meals for f in m.items)

    @property
    def sodium(self) -> float:
        return sum(f.sodium for m in self.meals for f in m.items)

    @property
    def price(self) -> float:
        return sum(m.price for m in self.meals)


@dataclass
class WeekPlan:
    """一周计划与汇总指标。"""

    target: DailyTarget
    days: list[DayPlan] = field(default_factory=list)
    budget: float | None = None
    goal_label: str = "减脂"

    @property
    def avg_kcal(self) -> float:
        return sum(d.kcal for d in self.days) / max(len(self.days), 1)

    @property
    def avg_protein(self) -> float:
        return sum(d.protein for d in self.days) / max(len(self.days), 1)

    @property
    def total_price(self) -> float:
        return sum(d.price for d in self.days)

    @property
    def protein_hit_days(self) -> int:
        return sum(1 for d in self.days if d.protein >= self.target.protein * 0.85)

    @property
    def over_budget(self) -> bool:
        if self.budget is None:
            return False
        return self.total_price > self.budget


def classify_food(food: Food) -> str:
    """把餐品分为 main / breakfast / side / drink。

    规则：先按名称分饮品/甜口，再按蛋白含量分主餐——
    蛋白 >= 10g 一律视为主餐（麦乐鸡、脆汁鸡等高蛋白小食也归入，保证蛋白目标可达成）。
    """
    name = food.name
    if any(k in name for k in DRINK_KEYS):
        return "drink"
    if any(k in name for k in BREAKFAST_KEYS):
        return "breakfast"
    if food.protein >= 10:
        return "main"
    if food.kcal >= 200 and food.protein >= 5:
        return "main"
    return "side"


def _combo_score(items: list[Food], slot: str, kcal_goal: float,
                 macro_goal: dict[str, float], price_weight: float,
                 recent: set[str], recent_bases: set[str]) -> float:
    kcal = sum(f.kcal for f in items)
    protein = sum(f.protein for f in items)
    fat = sum(f.fat for f in items)
    carb = sum(f.carb for f in items)
    sodium = sum(f.sodium for f in items)
    price = sum(f.price or 0.0 for f in items)

    # 权重：热量偏差 2.0，蛋白 3.0（高蛋白目标更难满足，重点倾斜），脂肪 0.6，碳水 0.4
    score = 2.0 * ((kcal - kcal_goal) / max(kcal_goal, 1.0)) ** 2
    score += 3.0 * ((protein - macro_goal["protein"]) / max(macro_goal["protein"], 1.0)) ** 2
    score += 0.6 * ((fat - macro_goal["fat"]) / max(macro_goal["fat"], 1.0)) ** 2
    score += 0.4 * ((carb - macro_goal["carb"]) / max(macro_goal["carb"], 1.0)) ** 2
    # 蛋白密度奖励：同样热量下蛋白越高越好
    if protein > 0:
        score += 0.06 * (kcal / protein) / 25.0
    if sodium > 800:  # 单餐钠软上限
        score += 0.5 * (sodium - 800) / 800
    score += price * price_weight
    bases = [_base_name(f.name) for f in items]
    score += 10.0 * (len(bases) - len(set(bases)))  # 同款（含不同杯型）重复选品，重罚
    for f in items:
        if f.name in recent or _base_name(f.name) in recent_bases:
            score += 0.5  # 多样性惩罚：最近一两天出现过
    return score


def _plan_meal(slot: str, kcal_goal: float, macro_goal: dict[str, float],
               pool: list[Food], rng: random.Random, recent: set[str],
               recent_bases: set[str], price_weight: float) -> Meal:
    if slot == "breakfast":
        # 早餐档只选早餐类主餐（麦满分/粥/炒双蛋堡等）
        mains = [f for f in pool if f.kind == "breakfast"] or \
                [f for f in pool if f.kind in ("main", "breakfast")]
    else:
        # 午晚餐不选早餐专属品
        mains = [f for f in pool if f.kind == "main"]
    drinks = [f for f in pool if f.kind == "drink"]
    sides = [f for f in pool if f.kind == "side"]
    if not mains:
        mains = pool or []
    # 高热量目标（增肌）允许每餐更多件数
    max_items = 4 if kcal_goal <= 800 else 5

    best_items: list[Food] = []
    best_score = float("inf")
    for _ in range(SEARCH_ROUNDS):
        # 高蛋白目标下允许一份餐里出现两个主餐（此时不再叠加小食，控制件数与花费）
        n_mains = 2 if (rng.random() < 0.30 and len(mains) > 1) else 1
        picked = rng.sample(mains, n_mains)
        items = list(picked)
        kcal = sum(f.kcal for f in items)
        if kcal > kcal_goal * 1.5:  # 双主餐也不能太超标
            continue
        if len(items) > max_items:
            continue
        if n_mains == 1:
            if sides and rng.random() < 0.4:
                side = rng.choice(sides)
                if side.name not in {f.name for f in items} \
                        and kcal + side.kcal <= kcal_goal * 1.3:
                    items.append(side)
                    kcal += side.kcal
            if drinks and rng.random() < 0.55:
                drink = rng.choice(drinks)
                if drink.name not in {f.name for f in items} \
                        and kcal + drink.kcal <= kcal_goal * 1.35:
                    items.append(drink)
        elif drinks and rng.random() < 0.35 and len(items) < max_items:
            drink = rng.choice(drinks)
            if drink.name not in {f.name for f in items} \
                    and kcal + drink.kcal <= kcal_goal * 1.2:
                items.append(drink)
        if len(items) > max_items:
            continue
        score = _combo_score(items, slot, kcal_goal, macro_goal,
                             price_weight, recent, recent_bases)
        if score < best_score:
            best_items, best_score = items, score
    if not best_items:  # 兜底：单个主餐
        best_items = [rng.choice(mains)]

    # 局部置换优化：逐个餐品尝试换成池中同类，得分更低则保留
    candidates = mains + sides + drinks
    for _ in range(2):
        improved = False
        for i in range(len(best_items)):
            for cand in candidates:
                if cand.name == best_items[i].name:
                    continue
                trial = list(best_items)
                trial[i] = cand
                if len({f.name for f in trial}) != len(trial):
                    continue  # 不引入重复
                score = _combo_score(trial, slot, kcal_goal, macro_goal,
                                     price_weight, recent, recent_bases)
                if score < best_score - 1e-9:
                    best_items, best_score = trial, score
                    improved = True
        if not improved:
            break
    return Meal(slot=slot, items=best_items)


def plan_week(
    foods: list[Food],
    target: DailyTarget,
    days: int = 7,
    budget: float | None = None,
    seed: int = 42,
    exclude: tuple[str, ...] = (),
    day_labels: list[str] | None = None,
    goal_label: str = "减脂",
) -> WeekPlan:
    """生成一周三餐计划。"""
    rng = random.Random(seed)
    pool = [f for f in foods if f.name not in exclude and f.kcal > 0]
    for f in pool:
        f.kind = classify_food(f)
    if not pool:
        raise ValueError("餐品池为空：请检查数据来源与忌口设置")

    # 设了预算就给价格一个恒定惩罚权重（元 -> 打分），让 planner 倾向高性价比餐品
    price_weight = 0.0 if budget is None else 0.003

    plan = WeekPlan(target=target, budget=budget, goal_label=goal_label)
    recent: list[str] = []
    recent_bases: list[str] = []
    for d in range(days):
        label = day_labels[d] if day_labels and d < len(day_labels) else f"第 {d + 1} 天"
        day = DayPlan(label=label)
        for slot in SLOTS:
            share = SLOT_SHARE[slot]
            kcal_goal = target.kcal * share
            macro_goal = {
                "protein": target.protein * share,
                "fat": target.fat * share,
                "carb": target.carb * share,
            }
            meal = _plan_meal(slot, kcal_goal, macro_goal, pool, rng,
                              set(recent), set(recent_bases), price_weight)
            day.meals.append(meal)
            recent.extend(f.name for f in meal.items)
            recent = recent[-8:]
            recent_bases.extend(_base_name(f.name) for f in meal.items)
            recent_bases = recent_bases[-8:]
        plan.days.append(day)
    return plan
