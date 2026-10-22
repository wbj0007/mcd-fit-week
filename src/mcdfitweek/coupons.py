"""优惠券解析、有效期判断与计划餐品匹配。

数据来源（实时模式，均为麦当劳 MCP 官方工具）：
- ``available-coupons``   麦麦省：当前可领取的优惠券列表
- ``query-my-coupons``    我的优惠券：账户下已领可用的券
- ``query-store-coupons`` 当前门店可用的优惠券
- ``campaign-calendar``   当月营销活动日历（回答"哪天有优惠活动"）

演示模式下使用 ``data/demo_coupons.json``（快照演示数据，报告中会明确标注）。

MCP 返回的券字段名没有公开文档保证，这里按常见字段名做宽容解析；
解析不出的条目保留名称，宁可少展示也不报错中断（诚实降级）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .nutrition import normalize_name

# 各语义字段的常见键名（按优先级尝试）
_NAME_KEYS = ("couponName", "couponTitle", "title", "name")
_DISCOUNT_KEYS = ("discountAmount", "discountPrice", "discount",
                  "offerPrice", "promotionPrice", "description", "desc")
_FROM_KEYS = ("validStartDate", "validStart", "startDate", "beginDate",
              "effectiveDate", "start", "beginTime")
_TO_KEYS = ("validEndDate", "validEnd", "endDate", "expireDate",
            "expiryDate", "end", "expireTime")
_PRODUCT_KEYS = ("productNames", "productName", "products", "productList",
                 "foodNames", "applicableProducts", "items")
_WEEKDAY_KEYS = ("weekdays", "availableWeekdays", "usableWeekdays",
                 "availableDays")
_SOURCE_KEYS = ("source", "couponType", "type", "channel")


def _get(d: dict, keys: tuple[str, ...]):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


@dataclass
class Coupon:
    """一张优惠券的归一化表示。"""

    name: str
    discount: str = ""              # 展示用优惠描述，如 "省 10 元"
    discount_value: float | None = None  # 可解析的金额（元）
    valid_from: str | None = None   # "YYYY-MM-DD"，None 表示不限
    valid_to: str | None = None
    weekdays: tuple[int, ...] = ()  # 0=周一 … 6=周日；空元组表示全周可用
    products: tuple[str, ...] = ()  # 适配餐品关键词（子串匹配归一化名称）
    source: str = ""                # 来源标签，如 麦麦省 / 门店券 / 演示数据


def _to_date(value) -> str | None:
    """把各种日期表示归一成 YYYY-MM-DD 字符串，失败返回 None。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit() and len(s) == 8:
        s = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    s = s.replace("/", "-").replace(".", "-")
    if " " in s:
        s = s.split(" ")[0]
    if "T" in s:
        s = s.split("T")[0]
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


def _parse_discount(raw) -> tuple[str, float | None]:
    if raw is None:
        return "", None
    if isinstance(raw, (int, float)):
        v = float(raw)
        return (f"省 {v:g} 元", v) if v > 0 else ("", None)
    text = str(raw).strip()
    if not text:
        return "", None
    value: float | None = None
    digits = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            digits += ch
        elif digits:
            break
    try:
        value = float(digits) if digits else None
    except ValueError:
        value = None
    return text, value


def _parse_products(raw) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = [raw]
    elif isinstance(raw, (list, tuple)):
        parts = []
        for item in raw:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                got = _get(item, ("productName", "name", "title", "foodName"))
                if got:
                    parts.append(str(got))
    else:
        return ()
    return tuple(p.strip() for p in parts if p and p.strip())


def parse_coupons(raw: list) -> list[Coupon]:
    """把 MCP 优惠券列表解析成 Coupon 对象（宽容解析，不抛异常）。"""
    coupons: list[Coupon] = []
    for item in raw or []:
        if isinstance(item, str):
            if item.strip():
                coupons.append(Coupon(name=item.strip()))
            continue
        if not isinstance(item, dict):
            continue
        # 兼容嵌套：券主体可能在 couponInfo / data 子对象里
        inner = item.get("couponInfo") if isinstance(item.get("couponInfo"), dict) else item
        name = _get(inner, _NAME_KEYS) or _get(item, _NAME_KEYS)
        if not name:
            continue
        discount_text, discount_value = _parse_discount(
            _get(inner, _DISCOUNT_KEYS) or _get(item, _DISCOUNT_KEYS))
        weekdays_raw = _get(inner, _WEEKDAY_KEYS) or _get(item, _WEEKDAY_KEYS)
        weekdays: list[int] = []
        if isinstance(weekdays_raw, (list, tuple)):
            for w in weekdays_raw:
                try:
                    weekdays.append(int(w) % 7)
                except (TypeError, ValueError):
                    continue
        source = _get(inner, _SOURCE_KEYS) or _get(item, _SOURCE_KEYS) or ""
        coupons.append(Coupon(
            name=str(name).strip(),
            discount=discount_text,
            discount_value=discount_value,
            valid_from=_to_date(_get(inner, _FROM_KEYS) or _get(item, _FROM_KEYS)),
            valid_to=_to_date(_get(inner, _TO_KEYS) or _get(item, _TO_KEYS)),
            weekdays=tuple(sorted(set(weekdays))),
            products=_parse_products(_get(inner, _PRODUCT_KEYS) or _get(item, _PRODUCT_KEYS)),
            source=str(source) if source else "",
        ))
    return coupons


def coupon_active_on(coupon: Coupon, d: date) -> bool:
    """判断券在某天是否可用。"""
    if coupon.valid_from and d < date.fromisoformat(coupon.valid_from):
        return False
    if coupon.valid_to and d > date.fromisoformat(coupon.valid_to):
        return False
    if coupon.weekdays and d.weekday() not in coupon.weekdays:
        return False
    return True


def match_food_names(coupon: Coupon, food_names: list[str]) -> list[str]:
    """返回计划中命中该券适配关键词的餐品名。"""
    if not coupon.products:
        return []
    matched: list[str] = []
    for fname in food_names:
        nf = normalize_name(fname)
        for key in coupon.products:
            nk = normalize_name(key)
            if nk and nk in nf:
                matched.append(fname)
                break
    return matched


@dataclass
class DayCoupons:
    """某一天计划可用的券信息。"""

    label: str
    entries: list[tuple[Coupon, list[str]]] = field(default_factory=list)

    @property
    def total_saving(self) -> float:
        return sum(c.discount_value or 0.0 for c, _ in self.entries)


def build_day_coupons(
    day_labels: list[str],
    day_dates: list[date],
    day_food_names: list[list[str]],
    coupons: list[Coupon],
) -> list[DayCoupons]:
    """按天计算计划涉及餐品可用的优惠券（用于报告展示）。"""
    result: list[DayCoupons] = []
    for label, d, foods in zip(day_labels, day_dates, day_food_names):
        dc = DayCoupons(label=label)
        seen: set[str] = set()
        for coupon in coupons:
            if not coupon_active_on(coupon, d):
                continue
            matched = match_food_names(coupon, foods)
            if matched and coupon.name not in seen:
                seen.add(coupon.name)
                dc.entries.append((coupon, matched))
        result.append(dc)
    return result


COUPON_ENTRANCE_HTML = """
<div class="coupon-entry">
  <div class="entry-title">优惠券在哪里领（入口说明）</div>
  <ul>
    <li><b>麦当劳 App</b>：首页「麦麦省」/「优惠券」频道选券领取；已领的券在「我的 → 卡包 / 优惠券」查看，点餐结算时勾选使用。</li>
    <li><b>微信小程序「麦当劳」</b>：首页「领券中心」领取，会员中心可查卡包；到店扫码点餐结算页同样可选券。</li>
    <li><b>MCP 数据侧</b>：available-coupons（麦麦省可领券）/ auto-bind-coupons（一键领券）/ query-my-coupons（我的可用券）/ campaign-calendar（营销活动日历，看哪天有活动）。</li>
  </ul>
  <div class="entry-note">{note}</div>
</div>
"""
