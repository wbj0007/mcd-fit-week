"""把 MCP 接口返回快照构建为演示数据（data/demo_*.json）。

数据来源：docs/samples/ 下为麦当劳 MCP 接口真实返回快照（2026-10-10），
本脚本仅做格式转换，供 --demo 模式离线运行与 README 演示使用。
正式运行时请使用 --token 走 MCP 实时数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcdfitweek.nutrition import parse_nutrition_table  # noqa: E402


def main() -> None:
    raw = (ROOT / "docs/samples/nutrition-raw.txt").read_text(encoding="utf-8")
    # 从快照文本中取出 data 字符串
    marker = '"data":"'
    start = raw.find(marker)
    if start < 0:
        raise SystemExit("快照中未找到 data 字段")
    body = raw[start + len(marker):]
    end = body.find('"}')  # data 字符串结束
    data_str = body[:end].replace("\\n", "\n").replace('\\"', '"')

    foods = parse_nutrition_table(data_str)
    nutrition_json = [
        {
            "name": f.name,
            "kcal": f.kcal,
            "protein": f.protein,
            "fat": f.fat,
            "carb": f.carb,
            "sodium": f.sodium,
            "calcium": f.calcium,
        }
        for f in foods
    ]
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "demo_nutrition.json").write_text(
        json.dumps(nutrition_json, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    menu = []
    for line in (ROOT / "docs/samples/menu-prices.txt").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        name, price = line.rsplit("|", 1)
        menu.append({"name": name, "price": float(price)})
    (out_dir / "demo_menu.json").write_text(
        json.dumps(menu, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"demo_nutrition.json: {len(nutrition_json)} 项")
    print(f"demo_menu.json: {len(menu)} 项")


if __name__ == "__main__":
    main()
