import re
from typing import Any

from core.state import AgentState


DEMO_DEFAULTS = {
    "origin": "台北",
    "departure_station": "台北車站",
    "destination": "台中",
    "start_date": "",
    "end_date": "",
    "days": 2,
    "nights": 1,
    "party_size": 1,
    "total_budget": 6000,
    "preference": "不要太趕、戶外景點",
    "hotel_preference": "交通方便",
    "transport_preference": "大眾運輸",
    "needs_booking": True,
    "needs_budget": True,
    "preferred_areas": ["台中車站", "逢甲"],
}

CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
}


def _extract_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    return CHINESE_NUMBERS.get(value, 0)


# 台灣主要縣市（含台/臺、常見旅遊地），用來抓「目的地/出發地」的城市 token
KNOWN_CITIES = (
    "台北", "臺北", "新北", "桃園", "台中", "臺中", "台南", "臺南", "高雄",
    "基隆", "新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭",
    "花蓮", "台東", "臺東", "澎湖", "金門", "馬祖", "墾丁", "九份",
)
_CITY_ALT = "|".join(KNOWN_CITIES)

# 中文數字 → 阿拉伯數字（支援 十/百/千/萬，用於預算與人數解析）
_ZH_DIGITS = {
    "零": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def _zh_section(token: str) -> int:
    """解析『萬』以下的中文數字段落，例如 三千五百 / 二十。"""
    if not token:
        return 0
    if token.isdigit():
        return int(token)
    total = 0
    current = 0
    for ch in token:
        if ch in _ZH_DIGITS:
            current = _ZH_DIGITS[ch]
        elif ch == "十":
            current = (current or 1) * 10
            total += current
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "千":
            total += (current or 1) * 1000
            current = 0
    return total + current


def _zh_amount_to_int(token: str):
    """把『兩萬』『一萬五』『15000』等金額字串轉成整數；無法解析回傳 None。"""
    token = token.strip().replace(",", "").replace("万", "萬")
    if not token:
        return None
    if token.isdigit():
        return int(token)
    if "萬" in token:
        left, _, right = token.partition("萬")
        man = _zh_section(left) if left else 1
        total = man * 10000
        if right:
            # 「一萬五」口語 = 15000：萬後單一個位數視為千
            if len(right) == 1 and right in _ZH_DIGITS:
                total += _ZH_DIGITS[right] * 1000
            else:
                total += _zh_section(right)
        return total
    value = _zh_section(token)
    return value or None


def _parse_dates(text: str) -> tuple[str, str]:
    match = re.search(r"(\d{1,2}/\d{1,2})\s*(?:[~-]|到|至)\s*(\d{1,2}/\d{1,2})", text)
    if match:
        return match.group(1), match.group(2)
    return str(DEMO_DEFAULTS["start_date"]), str(DEMO_DEFAULTS["end_date"])


def _parse_days_nights(text: str) -> tuple[int, int]:
    match = re.search(r"([一二兩三四五\d]+)\s*天\s*([一二兩三四五\d]+)\s*夜", text)
    if match:
        days = _extract_number(match.group(1))
        nights = _extract_number(match.group(2))
        if days and nights:
            return days, nights
    return int(DEMO_DEFAULTS["days"]), int(DEMO_DEFAULTS["nights"])


def _parse_budget(text: str) -> int:
    # 先抓阿拉伯數字（保留既有行為）
    match = re.search(r"(?:一人|每人)?(?:總)?預算\s*([0-9,]+)\s*(?:元|塊)?", text)
    if match:
        return int(match.group(1).replace(",", ""))
    # 再抓中文金額，例如「總預算兩萬元」
    match = re.search(r"預算\s*([零一二兩两三四五六七八九十百千萬万\d,]+)\s*(?:元|塊)?", text)
    if match:
        value = _zh_amount_to_int(match.group(1))
        if value:
            return value
    return int(DEMO_DEFAULTS["total_budget"])


def _parse_party_size(text: str) -> int:
    match = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*(?:人|位)", text)
    if match:
        token = match.group(1)
        count = int(token) if token.isdigit() else _zh_section(token)
        if count:
            return max(1, count)
    return int(DEMO_DEFAULTS["party_size"])


def _origin_from_departure(value: str) -> str:
    value = value.strip()
    if value.endswith("車站"):
        return value.removesuffix("車站")
    return value


def _parse_origin(text: str) -> str:
    match = re.search(r"從([^()（），,。]+)[(（][^()（）]*?車站出發?[)）]", text)
    if match:
        origin = _origin_from_departure(match.group(1))
        if origin:
            return origin

    for pattern in (
        r"從([^()（），,。]+?車站)出發",
        r"([^()（），,。]+?車站)出發[，,、]?\s*(?:到|去)",
        r"從([^()（），,。]+?)出發[，,、]?\s*(?:到|去)",
        r"從([^()（），,。]+?)(?:到|去)",
    ):
        match = re.search(pattern, text)
        if match:
            origin = _origin_from_departure(match.group(1))
            if origin:
                return origin

    return str(DEMO_DEFAULTS["origin"])


def _parse_departure_station(text: str) -> str:
    for pattern in (
        r"[(（]([^()（），,。]+?車站)出發?[)）]",
        r"從([^()（），,。]+?車站)出發",
        r"([^()（），,。]+?車站)出發",
        r"從([^()（），,。]+?)出發[，,、]?\s*(?:到|去)",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return str(DEMO_DEFAULTS["departure_station"])


def _parse_destination(text: str) -> str:
    # 1) 「去 / 到 / 玩 / 規劃 / 前往 + 城市」，例如「去台中」「幫我規劃台南」
    match = re.search(rf"(?:去|到|玩|遊|規劃|前往)\s*({_CITY_ALT})", text)
    if match:
        return match.group(1)

    # 2) 城市緊接在天數前，例如「台南三天兩夜」
    match = re.search(rf"({_CITY_ALT})(?=[一二兩三四五六七八九十\d]+\s*天)", text)
    if match:
        return match.group(1)

    # 3) 文中第一個「非出發地」的已知城市
    origin = _parse_origin(text)
    for candidate in re.finditer(rf"({_CITY_ALT})", text):
        if candidate.group(1) != origin:
            return candidate.group(1)

    # 4) 舊的寬鬆規則作為最後嘗試，再退回預設
    match = re.search(r"[去到]([^，,。()\s]+?)(?=[一二兩三四五\d]+\s*天|[，,。()\s]|$)", text)
    if match:
        destination = match.group(1).strip()
        if destination:
            return destination
    return str(DEMO_DEFAULTS["destination"])


def _parse_preference(text: str) -> str:
    keywords = (
        "不要太趕", "戶外景點", "美食", "文青", "親子", "購物", "歷史",
        "自然", "放鬆", "舒適", "省錢", "便宜", "踩點", "打卡", "夜市", "咖啡",
    )
    preferences = [kw for kw in keywords if kw in text]
    return "、".join(preferences) or str(DEMO_DEFAULTS["preference"])


def _parse_hotel_preference(text: str) -> str:
    if "交通方便" in text:
        return "交通方便"
    if "住宿" in text:
        return str(DEMO_DEFAULTS["hotel_preference"])
    return ""


def _parse_transport_preference(text: str) -> str:
    if "高鐵" in text:
        return "高鐵"
    if "台鐵" in text:
        return "台鐵"
    if "大眾運輸" in text or "公車" in text:
        return "大眾運輸"
    return str(DEMO_DEFAULTS["transport_preference"])


def parse_trip_request(text: str) -> dict[str, Any]:
    start_date, end_date = _parse_dates(text)
    days, nights = _parse_days_nights(text)
    needs_booking = "住宿" in text or "旅館" in text or "飯店" in text

    return {
        "origin": _parse_origin(text),
        "departure_station": _parse_departure_station(text),
        "destination": _parse_destination(text),
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "nights": nights,
        "party_size": _parse_party_size(text),
        "total_budget": _parse_budget(text),
        "preference": _parse_preference(text),
        "hotel_preference": _parse_hotel_preference(text),
        "transport_preference": _parse_transport_preference(text),
        "needs_booking": needs_booking or bool(DEMO_DEFAULTS["needs_booking"]),
        "needs_budget": True,
        "preferred_areas": list(DEMO_DEFAULTS["preferred_areas"]),
        "source": "rule_based_parser",
        "source_detail": "Parsed from user query using regex/rule-based parser.",
    }


def trip_parser_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages", [])
    text = str(messages[-1].content) if messages else str(state.get("user_query", ""))
    trip_request = parse_trip_request(text)

    return {
        "trip_request": trip_request,
        **trip_request,
        "current_task": "trip_parser",
        "next_step": "travel",
    }
