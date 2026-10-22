"""麦当劳中国 MCP 客户端（Streamable HTTP，仅标准库，无第三方依赖）。

协议要点（2026-10 实测）:
- 服务端无状态，不返回 mcp-session-id：每次 tools/call 前先 initialize 即可
- 工具返回为 content[].text，内嵌「字段说明 + Original Response」，
  业务 JSON 取文本中最后一个 ``{"success"`` 起始的对象
- 限流 600 次/分钟，营养表全量只需调用一次并本地缓存
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .nutrition import Food, align_menu_prices, parse_nutrition_table
DEFAULT_URL = "https://mcp.mcd.cn"


class McpError(RuntimeError):
    """MCP 调用失败。"""


class McdMcpClient:
    """麦当劳 MCP 最小客户端。"""

    def __init__(self, token: str | None = None, url: str = DEFAULT_URL):
        token = token or os.environ.get("MCD_MCP_TOKEN", "")
        if not token:
            raise McpError("缺少 MCP Token：请通过 --token 或环境变量 MCD_MCP_TOKEN 提供")
        self.url = url
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._id = 0

    # ---------- 协议层 ----------

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        payload: dict = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers=self._headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise McpError(f"MCP HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise McpError(f"MCP 网络错误: {e.reason}") from e
        return self._parse_rpc(body)

    @staticmethod
    def _parse_rpc(body: str) -> dict:
        # 兼容 SSE（data: 行）与纯 JSON 两种返回
        if body.lstrip().startswith(("data:", "event:")):
            chunks = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
            body = "\n".join(chunks)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise McpError("MCP 返回不是合法 JSON") from e
        if isinstance(data, dict) and data.get("error"):
            raise McpError(f"MCP RPC 错误: {data['error']}")
        return data.get("result", data) if isinstance(data, dict) else {}

    def initialize(self) -> None:
        self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcdfitweek", "version": "0.1.0"},
        })

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """调用工具并返回业务 JSON（含 success/code/data 的对象）。"""
        self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        for block in result.get("content", []):
            text = block.get("text", "") if isinstance(block, dict) else str(block)
            biz = _extract_business_json(text)
            if biz is not None:
                return biz
        raise McpError(f"工具 {name} 的返回中未找到业务 JSON")

    # ---------- 业务封装 ----------

    def list_nutrition_foods(self) -> list[Food]:
        biz = self.call_tool("list-nutrition-foods")
        return parse_nutrition_table(biz.get("data", ""))

    def now_time_info(self) -> dict:
        return self.call_tool("now-time-info")

    def query_nearby_stores(self, city: str, keyword: str = "麦当劳") -> list[dict]:
        biz = self.call_tool("query-nearby-stores", {
            "beType": 1, "searchType": 2, "city": city, "keyword": keyword,
        })
        data = biz.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("stores", "storeList", "list"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def query_meals(self, store_code: str) -> dict:
        """返回 {categories: [...], meals: {code: {...}}}。"""
        biz = self.call_tool("query-meals", {
            "storeCode": store_code, "orderType": 1, "beType": 1,
        })
        return biz.get("data") or {}

    def query_store_coupons(self, store_code: str) -> list[dict]:
        biz = self.call_tool("query-store-coupons", {
            "storeCode": store_code, "orderType": 1, "beType": 1,
        })
        data = biz.get("data")
        return data if isinstance(data, list) else []

    def available_coupons(self) -> list[dict]:
        """麦麦省：当前可领取的优惠券列表。"""
        biz = self.call_tool("available-coupons")
        data = biz.get("data")
        return data if isinstance(data, list) else []

    def query_my_coupons(self) -> list[dict]:
        """我的优惠券：账户下已领可用的券列表。"""
        biz = self.call_tool("query-my-coupons")
        data = biz.get("data")
        return data if isinstance(data, list) else []

    def campaign_calendar(self) -> dict:
        """当月营销活动日历（进行中 / 往期 / 未来日期的活动）。"""
        biz = self.call_tool("campaign-calendar")
        return biz.get("data") or {}

    def calculate_price(self, store_code: str, items: list[dict]) -> dict:
        biz = self.call_tool("calculate-price", {"storeCode": store_code, "items": items})
        return biz.get("data") or {}


def _extract_business_json(text: str) -> dict | None:
    """从工具返回文本中提取最后一个业务 JSON 对象。"""
    idx = text.rfind('{"success"')
    if idx < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[idx:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


# ---------- 演示数据（无需 Token 的本地样例，来自 MCP 返回快照） ----------

def find_data_dir() -> Path:
    """定位仓库根目录下的 data/（演示数据）。"""
    candidates = [
        Path.cwd() / "data",
        Path(__file__).resolve().parent.parent.parent / "data",
    ]
    for path in candidates:
        if (path / "demo_nutrition.json").exists():
            return path
    return candidates[0]


def load_demo_foods() -> list[Food]:
    """加载演示数据：营养表 + 菜单价格对齐后的餐品池。"""
    data_dir = find_data_dir()
    nutrition = json.loads((data_dir / "demo_nutrition.json").read_text(encoding="utf-8"))
    menu = json.loads((data_dir / "demo_menu.json").read_text(encoding="utf-8"))

    foods = [Food(**row) for row in nutrition]
    matched = align_menu_prices(foods, menu)
    print(f"[demo] 营养 {len(foods)} 项，菜单价格匹配 {matched} 项", file=sys.stderr)
    return foods


def load_demo_coupons() -> list[dict]:
    """加载演示优惠券（快照数据，报告中会标注为演示）。"""
    data_dir = find_data_dir()
    path = data_dir / "demo_coupons.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
