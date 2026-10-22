"""命令行入口：python -m mcdfitweek

示例（演示模式，无需 Token）::

    python -m mcdfitweek --height 175 --weight 70 --age 28 --gender male \
        --goal cut --budget 250 --demo -o report.html

示例（实时模式，走麦当劳 MCP）::

    export MCD_MCP_TOKEN="你的Token"
    python -m mcdfitweek --height 175 --weight 70 --age 28 --gender male --goal cut
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

from .coupons import build_day_coupons, parse_coupons
from .mcp_client import McdMcpClient, load_demo_coupons, load_demo_foods
from .nutrition import (ACTIVITY_FACTORS, GOAL_LABELS, align_menu_prices,
                        apples_equivalent, daily_target)
from .planner import plan_week
from .report import render_report

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcdfitweek",
        description="麦麦轻食周计划：基于麦当劳中国 MCP 的一周三餐规划",
    )
    p.add_argument("--height", type=float, required=True, help="身高 cm")
    p.add_argument("--weight", type=float, required=True, help="体重 kg")
    p.add_argument("--age", type=int, required=True, help="年龄")
    p.add_argument("--gender", choices=["male", "female"], required=True)
    p.add_argument("--activity", default="moderate", choices=sorted(ACTIVITY_FACTORS))
    p.add_argument("--goal", default="cut", choices=sorted(GOAL_LABELS))
    p.add_argument("--days", type=int, default=7, help="规划天数，默认 7")
    p.add_argument("--budget", type=float, default=None, help="本周预算（元）")
    p.add_argument("--city", default="上海市", help="实时模式下的门店城市")
    p.add_argument("--exclude", default="", help="忌口餐品名，逗号分隔")
    p.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    p.add_argument("--token", default=None, help="MCP Token，也可用环境变量 MCD_MCP_TOKEN")
    p.add_argument("--demo", action="store_true", help="使用内置演示数据，无需 Token")
    p.add_argument("-o", "--output", default="mcd-fit-week-report.html", help="报告输出路径")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    target = daily_target(args.gender, args.weight, args.height, args.age,
                          args.activity, args.goal)
    exclude = tuple(s.strip() for s in args.exclude.split(",") if s.strip())

    start = date.today()
    labels = [f"{(start + timedelta(days=i)).strftime('%m-%d')} "
              f"{WEEKDAYS[(start + timedelta(days=i)).weekday()]}" for i in range(args.days)]
    week_range = f"{labels[0]} 至 {labels[-1]}"

    if args.demo:
        foods = load_demo_foods()
        raw_coupons = load_demo_coupons()
        data_source = "演示数据（麦当劳 MCP 返回快照）"
        coupon_note = "当前为演示模式，券为演示数据；领券入口以麦当劳官方 App / 小程序实际为准。"
        print(f"[demo] 使用内置演示数据，共 {len(foods)} 项餐品", file=sys.stderr)
    else:
        client = McdMcpClient(args.token or os.environ.get("MCD_MCP_TOKEN"))
        foods = client.list_nutrition_foods()
        data_source = "麦当劳中国 MCP（实时）"
        coupon_note = "优惠券来自麦当劳 MCP 实时接口（available-coupons / query-my-coupons）。"
        print(f"[live] 拉取到 {len(foods)} 项官方营养数据", file=sys.stderr)
        raw_coupons = []
        try:
            raw_coupons = client.available_coupons()
            print(f"[live] 麦麦省可领券 {len(raw_coupons)} 张", file=sys.stderr)
            my_coupons = client.query_my_coupons()
            print(f"[live] 我的可用券 {len(my_coupons)} 张", file=sys.stderr)
            raw_coupons = raw_coupons + my_coupons
            try:
                calendar = client.campaign_calendar()
                activities = calendar.get("activities") or calendar.get("list") or []
                print(f"[live] 本月营销活动 {len(activities)} 场（详见 campaign-calendar）",
                      file=sys.stderr)
            except Exception as e:  # 活动日历失败不影响券与规划
                print(f"[live] 活动日历获取失败: {e}", file=sys.stderr)
        except Exception as e:  # 优惠券失败不阻塞规划
            print(f"[live] 优惠券获取失败，报告中将只展示领券入口: {e}", file=sys.stderr)
        try:
            stores = client.query_nearby_stores(args.city)
            if stores:
                store_code = stores[0].get("storeCode") or stores[0].get("beCode")
                print(f"[live] 门店: {stores[0].get('storeName', store_code)}",
                      file=sys.stderr)
                menu = client.query_meals(store_code)
                meals = menu.get("meals", {})
                matched = align_menu_prices(foods, list(meals.values()))
                store_coupons = client.query_store_coupons(store_code)
                raw_coupons = raw_coupons + store_coupons
                print(f"[live] 菜单 {len(meals)} 项，价格匹配 {matched} 项，"
                      f"门店可用券 {len(store_coupons)} 张", file=sys.stderr)
        except Exception as e:  # 门店/菜单失败不阻塞规划
            print(f"[live] 门店信息获取失败，仅用营养数据: {e}", file=sys.stderr)

    coupons = parse_coupons(raw_coupons)
    print(f"[coupon] 解析到优惠券 {len(coupons)} 张", file=sys.stderr)

    plan = plan_week(
        foods, target, days=args.days, budget=args.budget,
        seed=args.seed, exclude=exclude, day_labels=labels,
        goal_label=GOAL_LABELS[args.goal],
    )

    day_dates = [start + timedelta(days=i) for i in range(args.days)]
    day_food_names = [
        [f.name for m in day.meals for f in m.items] for day in plan.days
    ]
    day_coupons = build_day_coupons(labels, day_dates, day_food_names, coupons)
    n_days_with_coupons = sum(1 for dc in day_coupons if dc.entries)

    html_text = render_report(
        plan, height_cm=args.height, weight_kg=args.weight, goal=args.goal,
        week_range=week_range, data_source=data_source,
        day_coupons=day_coupons, coupon_note=coupon_note,
    )
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(html_text)

    print(f"目标: {target.kcal:.0f} kcal/日（{apples_equivalent(target.kcal)}）, "
          f"蛋白 {target.protein:.0f} g/日 ({GOAL_LABELS[args.goal]})")
    print(f"计划: {len(plan.days)} 天, 平均 {plan.avg_kcal:.0f} kcal/日"
          f"（{apples_equivalent(plan.avg_kcal)}）, "
          f"蛋白达标 {plan.protein_hit_days}/{len(plan.days)} 天")
    print(f"券: 共 {len(coupons)} 张, {n_days_with_coupons}/{len(plan.days)} 天"
          f"计划餐品有券可用（入口与明细见报告）")
    if plan.budget is not None:
        flag = "（超预算）" if plan.over_budget else "（预算内）"
        print(f"总价: ¥{plan.total_price:,.1f} / 预算 ¥{plan.budget:,.1f} {flag}")
    print(f"报告已生成: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
