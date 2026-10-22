"""核心逻辑单元测试：营养表解析、名称对齐、目标计算、规划器。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcdfitweek.nutrition import (  # noqa: E402
    DailyTarget, Food, align_menu_prices, bmr_mifflin, daily_target,
    normalize_name, parse_nutrition_table,
)
from mcdfitweek.planner import plan_week  # noqa: E402

SAMPLE_TABLE = (
    "[3]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,"
    "carbohydrate,sodium,calcium}:\n"
    "  巨无霸,null,2146,513,27,26,42,961,171\n"
    "  纯悦,能量约清水1杯,0,0,0,0,0,0,0\n"
    "  小杯玉米杯,null,223,53,2,1,7,1,6\n"
    "  小杯玉米杯,null,223,53,2,1,7,1,6\n"
)


def test_parse_nutrition_table_dedup_and_values():
    foods = parse_nutrition_table(SAMPLE_TABLE)
    assert len(foods) == 3  # 重复行去重
    big_mac = foods[0]
    assert big_mac.name == "巨无霸"
    assert big_mac.kcal == 513
    assert big_mac.protein == 27
    assert big_mac.sodium == 961
    # 描述列含"逗号以外内容"时数值列仍从右侧正确切分
    water = foods[1]
    assert water.kcal == 0 and water.name == "纯悦"


def test_parse_nutrition_table_handles_comma_in_description():
    raw = ("[1]{productName,nutritionDescription,energyKj,energyKcal,protein,"
           "fat,carbohydrate,sodium,calcium}:\n"
           "  测试餐品,描述,含逗号,100,25,5,1,3,50,10\n")
    foods = parse_nutrition_table(raw)
    assert len(foods) == 1
    assert foods[0].kcal == 25 and foods[0].protein == 5


def test_normalize_name_strips_combo_and_spec():
    assert normalize_name("巨无霸三件套") == "巨无霸"
    assert normalize_name("麦辣鸡腿汉堡四件套") == "麦辣鸡腿汉堡"
    assert normalize_name("纯牛奶（盒装）") == "纯牛奶(盒装)"
    assert normalize_name("100% 苹果汁(盒装)") == "100%苹果汁(盒装)"


def test_align_menu_prices_prefers_single_over_combo():
    foods = [Food("巨无霸", 513, 27, 26, 42)]
    menu = [
        {"name": "巨无霸三件套", "price": 36.5},
        {"name": "巨无霸", "price": 25.5},
    ]
    matched = align_menu_prices(foods, menu)
    assert matched == 1
    assert foods[0].price == 25.5  # 单品价优先于套餐价


def test_align_menu_prices_imputes_missing():
    foods = [Food("麦满分A", 300, 15, 10, 35), Food("神秘餐品", 480, 20, 15, 40)]
    menu = [{"name": "麦满分A", "price": 18.0}, {"name": "牛堡", "price": 25.0}]
    align_menu_prices(foods, menu)
    assert foods[0].price == 18.0
    assert foods[1].price is not None and foods[1].price > 0  # 估算价


def test_bmr_and_daily_target():
    # Mifflin-St Jeor: 男 70kg 175cm 28岁 = 700 + 1093.75 - 140 + 5
    assert bmr_mifflin("male", 70, 175, 28) == pytest.approx(1658.75, abs=0.1)
    assert bmr_mifflin("female", 55, 160, 26) == pytest.approx(1259.0, abs=0.1)
    t = daily_target("male", 70, 175, 28, "moderate", "cut")
    assert isinstance(t, DailyTarget)
    # TDEE 1658.75*1.55=2571, 减脂 x0.8 ≈ 2057
    assert 1950 <= t.kcal <= 2150
    assert t.protein == 112  # 1.6 g/kg
    # 宏量加总应约等于总热量
    assert t.protein * 4 + t.fat * 9 + t.carb * 4 == pytest.approx(t.kcal, rel=0.02)


def _rich_pool() -> list[Food]:
    """构造一个足够大的测试餐品池。"""
    items = [
        ("巨无霸", 513, 27, 26, 42, 961), ("麦辣鸡腿汉堡", 485, 24, 24, 42, 1208),
        ("板烧鸡腿堡", 391, 23, 17, 35, 1041), ("麦香鱼", 325, 16, 13, 35, 556),
        ("双层吉士汉堡", 429, 27, 22, 31, 1017), ("培根蔬萃双层牛堡", 442, 24, 23, 34, 728),
        ("不素之霸双层牛堡", 493, 28, 27, 34, 1012), ("汉堡包", 248, 13, 8, 29, 492),
        ("猪柳蛋麦满分", 387, 23, 21, 25, 846), ("烟肉蛋麦满分", 260, 16, 10, 24, 483),
        ("原味板烧鸡腿麦满分", 246, 15, 9, 25, 611), ("皮蛋鸡肉粥", 133, 6, 3, 20, 611),
        ("麦乐鸡5块", 213, 12, 12, 13, 422), ("那么大鸡排", 385, 24, 21, 24, 996),
        ("麦麦脆汁鸡-琵琶腿", 328, 21, 20, 16, 905), ("中薯条", 289, 4, 12, 38, 165),
        ("大薯条", 379, 6, 16, 50, 216), ("苹果片", 32, 0, 0, 7, 0),
        ("可乐中杯", 147, 0, 0, 36, 0), ("无糖可口可乐中杯", 0, 0, 0, 1, 35),
        ("鲜萃咖啡", 13, 1, 0, 0, 3), ("优品豆浆大杯", 202, 8, 4, 33, 43),
        ("纯牛奶（盒装）", 129, 7, 7, 10, 73), ("圆筒冰淇淋", 93, 2, 3, 14, 36),
        ("香芋派", 232, 2, 12, 28, 159),
    ]
    return [Food(n, k, p, f, c, s, price=15.0) for n, k, p, f, c, s in items]


def test_plan_week_demo_pool():
    foods = _rich_pool()
    target = daily_target("male", 70, 175, 28, "moderate", "cut")
    plan = plan_week(foods, target, days=7, budget=500, seed=42)
    assert len(plan.days) == 7
    # 平均热量应落在目标 ±20% 内
    assert plan.avg_kcal == pytest.approx(target.kcal, rel=0.2)
    # 池足够大时，当日不应有重复选品（含杯型）
    from mcdfitweek.planner import _base_name
    for day in plan.days:
        bases = [_base_name(f.name) for m in day.meals for f in m.items]
        assert len(bases) == len(set(bases)), day.label


def test_plan_week_exclude():
    foods = parse_nutrition_table(SAMPLE_TABLE) + [
        Food("麦辣鸡腿汉堡", 485, 24, 24, 42),
    ]
    target = daily_target("male", 70, 175, 28, "moderate", "cut")
    plan = plan_week(foods, target, days=3, exclude=("巨无霸",), seed=1)
    names = {f.name for d in plan.days for m in d.meals for f in m.items}
    assert "巨无霸" not in names


def test_apples_equivalent():
    from mcdfitweek.nutrition import apples_equivalent
    assert apples_equivalent(0) == "0 个苹果"
    assert apples_equivalent(30) == "不到半个苹果"
    assert apples_equivalent(95) == "约 1 个苹果"
    assert apples_equivalent(475) == "约 5 个苹果"
    assert "苹果" in apples_equivalent(2057)


def _demo_coupons() -> list[dict]:
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "data" / "demo_coupons.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_parse_and_match_coupons():
    from datetime import date

    from mcdfitweek.coupons import (build_day_coupons, coupon_active_on,
                                    match_food_names, parse_coupons)
    coupons = parse_coupons(_demo_coupons())
    assert len(coupons) == 8
    big_mac = next(c for c in coupons if "巨无霸" in c.name)
    assert big_mac.weekdays == (0, 1, 2, 3, 4)
    assert big_mac.discount_value == 10.0

    # 周一（2026-10-19）可用巨无霸券，周日不可用
    assert coupon_active_on(big_mac, date(2026, 10, 19))
    assert not coupon_active_on(big_mac, date(2026, 10, 25))

    # 子串匹配：麦辣鸡腿 关键词应命中 麦辣鸡腿汉堡 与 三件套名
    spicy = next(c for c in coupons if "买一送一" in c.name and "麦辣" in c.name)
    matched = match_food_names(spicy, ["麦辣鸡腿汉堡", "麦辣鸡腿汉堡三件套", "板烧鸡腿堡"])
    assert matched == ["麦辣鸡腿汉堡", "麦辣鸡腿汉堡三件套"]

    # 关键词族匹配：牛堡券应命中 培根蔬萃双层牛堡 等牛堡家族
    beef = next(c for c in coupons if c.name == "经典牛堡立减券")
    assert match_food_names(beef, ["培根蔬萃双层牛堡", "麦香鱼"]) == ["培根蔬萃双层牛堡"]

    # 按天聚合：2026-10-21（周三）麦辣券与鳕鱼券生效，麦乐鸡/豆浆券（周二）不生效
    labels = ["10-21 周三"]
    dc = build_day_coupons(labels, [date(2026, 10, 21)],
                           [["麦辣鸡腿汉堡", "双层深海鳕鱼堡", "中薯条"]], coupons)
    names = {c.name for c, _ in dc[0].entries}
    assert "麦辣鸡腿堡买一送一券" in names and "深海鳕鱼堡买一送一券" in names
    assert "优品豆浆半价券" not in names
    assert dc[0].total_saving == 23.5 + 24.0


def test_parse_coupons_tolerant():
    from mcdfitweek.coupons import parse_coupons
    raw = [
        "纯字符串券名",
        {"couponName": "嵌套券", "couponInfo": {
            "validStartDate": "20261019", "validEndDate": "2026/10/25",
            "discountAmount": 8, "productNames": ["麦香鱼"]}},
        {"foo": "bar"},       # 无名称，跳过
        42,                   # 非法类型，跳过
    ]
    coupons = parse_coupons(raw)
    assert len(coupons) == 2
    nested = coupons[1]
    assert nested.valid_from == "2026-10-19" and nested.valid_to == "2026-10-25"
    assert nested.discount_value == 8.0
