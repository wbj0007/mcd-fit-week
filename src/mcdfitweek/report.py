"""生成自包含的可分享 HTML 周计划报告。"""

from __future__ import annotations

import html
from datetime import date

from .coupons import COUPON_ENTRANCE_HTML, DayCoupons
from .nutrition import GOAL_LABELS, apples_equivalent
from .planner import SLOT_LABELS, WeekPlan

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
       background: #F7F6F2; color: #2C2C2A; padding: 32px 20px; }
.wrap { max-width: 960px; margin: 0 auto; }
.hero { background: #fff; border-radius: 16px; padding: 28px 32px;
        border: 0.5px solid rgba(0,0,0,.08); margin-bottom: 16px; }
.hero h1 { font-size: 24px; font-weight: 600; }
.hero .sub { color: #5F5E5A; font-size: 13px; margin-top: 6px; }
.hero .tag { display: inline-block; background: #FAEEDA; color: #854F0B;
             font-size: 12px; padding: 3px 10px; border-radius: 999px; margin-right: 6px; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
.metric { background: #F1EFE8; border-radius: 10px; padding: 14px 16px; }
.metric .label { font-size: 12px; color: #5F5E5A; }
.metric .value { font-size: 22px; font-weight: 600; margin-top: 2px; }
.metric .unit { font-size: 12px; color: #888780; font-weight: 400; }
.summary { background: #fff; border-radius: 16px; padding: 20px 32px;
           border: 0.5px solid rgba(0,0,0,.08); margin-bottom: 16px;
           display: flex; gap: 32px; flex-wrap: wrap; }
.summary .item .k { font-size: 12px; color: #5F5E5A; }
.summary .item .v { font-size: 18px; font-weight: 600; margin-top: 2px; }
.days { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.day { background: #fff; border-radius: 16px; padding: 18px 20px;
       border: 0.5px solid rgba(0,0,0,.08); }
.day h2 { font-size: 15px; font-weight: 600; display: flex; justify-content: space-between; }
.day h2 .kcal { color: #854F0B; font-size: 13px; font-weight: 500; }
.meal { margin-top: 12px; }
.meal .slot { font-size: 12px; color: #0F6E56; font-weight: 500; }
.meal .items { font-size: 13px; margin-top: 3px; line-height: 1.7; }
.meal .items .p { color: #888780; font-size: 12px; }
.bar { height: 6px; background: #F1EFE8; border-radius: 3px; margin-top: 10px; overflow: hidden; }
.bar > div { height: 100%; border-radius: 3px; }
.day .total { font-size: 12px; color: #5F5E5A; margin-top: 8px; }
.warn { background: #FCEBEB; color: #791F1F; border-radius: 10px; padding: 12px 16px;
        font-size: 13px; margin-bottom: 16px; }
.coupons { background: #fff; border-radius: 16px; padding: 20px 32px;
           border: 0.5px solid rgba(0,0,0,.08); margin-bottom: 16px; }
.coupons h3 { font-size: 15px; font-weight: 600; margin-bottom: 10px; }
.coupons .coupon-day { font-size: 13px; line-height: 1.9; }
.coupons .coupon-day b { color: #854F0B; }
.coupons .coupon-item { color: #2C2C2A; }
.coupons .coupon-item .saving { color: #0F6E56; font-weight: 500; }
.coupons .coupon-none { color: #888780; font-size: 13px; }
.coupon-entry { background: #F1EFE8; border-radius: 10px; padding: 14px 18px;
                font-size: 13px; margin-top: 14px; }
.coupon-entry .entry-title { font-weight: 600; margin-bottom: 6px; }
.coupon-entry ul { padding-left: 18px; line-height: 1.9; }
.coupon-entry .entry-note { color: #888780; margin-top: 6px; font-size: 12px; }
.apple { color: #888780; font-size: 12px; font-weight: 400; }
.foot { color: #888780; font-size: 12px; text-align: center; margin-top: 24px; line-height: 1.8; }
@media (max-width: 720px) { .days { grid-template-columns: 1fr; } .metrics { grid-template-columns: repeat(2, 1fr); } }
"""


def _fmt_money(v: float) -> str:
    return f"¥{v:,.1f}"


def render_report(
    plan: WeekPlan,
    height_cm: float,
    weight_kg: float,
    goal: str,
    week_range: str,
    data_source: str,
    day_coupons: list[DayCoupons] | None = None,
    coupon_note: str = "",
) -> str:
    """渲染完整 HTML 报告字符串。"""
    t = plan.target
    goal_label = GOAL_LABELS.get(goal, plan.goal_label)
    day_coupons = day_coupons or []

    metrics = f"""
    <div class="metrics">
      <div class="metric"><div class="label">每日目标热量</div>
        <div class="value">{t.kcal:,.0f}<span class="unit"> kcal</span>
          <span class="apple">（{apples_equivalent(t.kcal)}）</span></div></div>
      <div class="metric"><div class="label">蛋白质</div>
        <div class="value">{t.protein:,.0f}<span class="unit"> g</span></div></div>
      <div class="metric"><div class="label">脂肪</div>
        <div class="value">{t.fat:,.0f}<span class="unit"> g</span></div></div>
      <div class="metric"><div class="label">碳水化合物</div>
        <div class="value">{t.carb:,.0f}<span class="unit"> g</span></div></div>
    </div>"""

    budget_text = _fmt_money(plan.budget) if plan.budget else "未设置"
    summary = f"""
    <div class="summary">
      <div class="item"><div class="k">周计划总价</div>
        <div class="v">{_fmt_money(plan.total_price)}</div></div>
      <div class="item"><div class="k">周预算</div><div class="v">{budget_text}</div></div>
      <div class="item"><div class="k">平均日热量</div>
        <div class="v">{plan.avg_kcal:,.0f} kcal
          <span style="font-size:12px;color:#888780;font-weight:400">（{apples_equivalent(plan.avg_kcal)}）</span></div></div>
      <div class="item"><div class="k">平均日蛋白</div>
        <div class="v">{plan.avg_protein:,.0f} g</div></div>
      <div class="item"><div class="k">蛋白达标天数</div>
        <div class="v">{plan.protein_hit_days} / {len(plan.days)} 天</div></div>
    </div>"""

    warn = ""
    if plan.over_budget:
        warn = (f'<div class="warn">本周总价 {_fmt_money(plan.total_price)} 已超出预算 '
                f'{_fmt_money(plan.budget)}。建议减少小食/饮品、或选择更低价的主餐，'
                f'计划不会为了凑预算而虚报热量。</div>')

    # ---------- 优惠券攻略 ----------
    coupon_rows = []
    week_saving = 0.0
    for dc in day_coupons:
        if not dc.entries:
            continue
        parts = []
        for coupon, foods in dc.entries:
            saving = f'<span class="saving">{html.escape(coupon.discount)}</span>' \
                if coupon.discount else ""
            src = f'[{html.escape(coupon.source)}]' if coupon.source else ""
            parts.append(
                f'<span class="coupon-item">{html.escape(coupon.name)}{src} {saving}'
                f' → 适用：{html.escape("、".join(sorted(set(foods))))}</span>')
        week_saving += dc.total_saving
        coupon_rows.append(
            f'<div class="coupon-day"><b>{html.escape(dc.label)}</b>：'
            f'{"；".join(parts)}</div>')
    if coupon_rows:
        saving_line = (f'<div class="coupon-day" style="margin-top:8px">'
                       f'按券面额粗略估算，本周计划餐品最多可省 '
                       f'<span class="saving">¥{week_saving:,.1f}</span>'
                       f'（同一天多张券不可叠加，实际以结算为准）。</div>')
        coupons_html = f"""
  <div class="coupons">
    <h3>优惠券攻略 · 本周计划涉及餐品哪天有券</h3>
    {''.join(coupon_rows)}
    {saving_line}
    {COUPON_ENTRANCE_HTML.format(note=coupon_note)}
  </div>"""
    else:
        coupons_html = f"""
  <div class="coupons">
    <h3>优惠券攻略</h3>
    <div class="coupon-none">当前数据源下未获取到计划餐品可用的优惠券；
      可在麦当劳 App「麦麦省 / 优惠券」或微信小程序「麦当劳 → 领券中心」查看当日券。</div>
    {COUPON_ENTRANCE_HTML.format(note=coupon_note)}
  </div>"""

    days_html = []
    for day in plan.days:
        pct = min(100.0, day.kcal / t.kcal * 100)
        protein_pct = min(100.0, day.protein / t.protein * 100)
        meals_html = []
        for meal in day.meals:
            items = "、".join(
                f'{html.escape(f.name)} <span class="p">{f.kcal:.0f} kcal</span>'
                for f in meal.items
            )
            meals_html.append(
                f'<div class="meal"><div class="slot">{SLOT_LABELS[meal.slot]}'
                f' · {meal.kcal:.0f} kcal（{apples_equivalent(meal.kcal)}）'
                f' · 蛋白 {meal.protein:.0f} g</div>'
                f'<div class="items">{items}</div></div>'
            )
        days_html.append(f"""
      <div class="day">
        <h2><span>{html.escape(day.label)}</span>
            <span class="kcal">{day.kcal:,.0f} / {t.kcal:,.0f} kcal
              <span style="font-weight:400">（{apples_equivalent(day.kcal)}）</span></span></h2>
        {''.join(meals_html)}
        <div class="bar"><div style="width:{pct:.0f}%;background:#EF9F27;"></div></div>
        <div class="total">蛋白 {day.protein:.0f}/{t.protein:.0f} g
          ({protein_pct:.0f}%) · 脂肪 {day.fat:.0f} g · 碳水 {day.carb:.0f} g
          · 钠 {day.sodium:.0f} mg · {_fmt_money(day.price)}</div>
      </div>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>麦麦轻食周计划 · {html.escape(week_range)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>麦麦轻食周计划 <span style="font-size:13px;color:#888780;font-weight:400">McFit Week</span></h1>
    <div class="sub">
      <span class="tag">{goal_label}</span>
      <span class="tag">{height_cm:.0f} cm / {weight_kg:.0f} kg</span>
      <span class="tag">{html.escape(week_range)}</span>
    </div>
    {metrics}
  </div>
  {warn}
  {summary}
  {coupons_html}
  <div class="days">{''.join(days_html)}</div>
  <div class="foot">
    数据来源：{html.escape(data_source)}<br>
    热量直观换算：1 个中等苹果 ≈ 95 kcal（USDA medium apple，约 182 g 可食部）。<br>
    本报告由「麦麦轻食周计划」自动生成，仅供参考，不构成医疗或营养专业建议；
    餐品信息、价格、优惠券及供应情况以麦当劳官方渠道实时结果为准。
  </div>
</div>
</body>
</html>"""
