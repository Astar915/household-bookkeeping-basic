from __future__ import annotations

import calendar
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .food_categories import FOOD_GROUP_LABELS, FOOD_GROUP_TO_CLASSIFICATION, classify_food_name


PURCHASES_AS_EATEN_SETTING = "food_review_purchases_count_as_eaten"


_REVIEW_PATTERNS = (
    r"吃了什么",
    r"吃过什么",
    r"都吃了",
    r"都吃过",
    r"吃了哪些",
    r"吃过哪些",
    r"饮食(?:记录|回顾|总结|分析|情况|搭配|怎么样)",
    r"食用记录",
    r"食物记录",
    r"缺什么营养",
    r"营养(?:不足|缺乏)",
    r"(?:缺|不足).{0,8}营养",
    r"(?:最近|近|过去|这段期间).{0,12}(?:吃|饮食|食物记录)",
)

_FRUIT_TERMS = (
    "水果", "果物", "フルーツ", "りんご", "林檎", "みかん", "バナナ", "ぶどう", "葡萄",
    "いちご", "苺", "もも", "桃", "梨", "キウイ", "オレンジ", "レモン", "アボカド",
    "メロン", "すいか", "スイカ", "苹果", "橘子", "橙子", "香蕉", "葡萄", "草莓", "桃子",
    "猕猴桃", "柠檬", "牛油果", "西瓜", "apple", "orange", "banana", "grape", "strawberry",
    "peach", "pear", "kiwi", "lemon", "avocado", "melon", "fruit",
)
_DAIRY_TERMS = (
    "牛乳", "牛奶", "ミルク", "ヨーグルト", "チーズ", "バター", "生クリーム", "乳製品",
    "低脂乳", "低脂肪乳", "低脂牛乳", "低脂肪牛乳", "乳飲料",
    "酸奶", "奶酪", "黄油", "鲜奶油", "milk", "low-fat milk", "low fat milk", "yogurt", "yoghurt", "cheese", "butter", "dairy",
)
_PROTEIN_TERMS = (
    "肉", "鸡蛋", "卵", "たまご", "玉子", "鸡肉", "牛肉", "猪肉", "豚肉", "鶏肉", "鱼", "魚",
    "鶏むね", "鶏もも", "ひき肉", "挽肉", "豆腐", "纳豆", "大豆", "毛豆", "枝豆", "豆类", "豆制品", "豆浆", "豆乳", "beef", "pork",
    "chicken", "meat", "egg", "fish", "seafood", "tofu", "natto", "soybean", "edamame", "beans",
)

_GROUPS = (
    ("staple", "主食粮食", "米饭、燕麦、全麦面包等主食"),
    ("vegetables", "蔬菜", "菠菜、西兰花、胡萝卜等不同颜色的蔬菜"),
    ("protein", "蛋白质来源", "鸡蛋、豆腐/纳豆、鱼或禽肉，轮换选择"),
    ("dairy", "奶类", "牛奶、酸奶；如不食用乳制品，可考虑钙强化替代品"),
    ("fruit", "水果", "柑橘、苹果、香蕉等当季水果，轮换选择"),
)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _contains(name: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = _normalize(term)
        if normalized.isascii() and normalized.replace(" ", "").isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", name):
                return True
        elif normalized in name:
            return True
    return False


def _nutrition_tags(item_name: str, recorded_group: str | None = None) -> set[str]:
    """Tag only recognizable food names; this is coverage, not nutrient analysis."""
    normalized = _normalize(item_name)
    food_group = recorded_group or classify_food_name(item_name)
    tags: set[str] = set()
    if food_group == "grains_staples":
        tags.add("staple")
    if food_group == "vegetables_fruits":
        tags.add("fruit" if _contains(normalized, _FRUIT_TERMS) else "vegetables")
    if food_group in {"seafood", "beans_tofu"} or _contains(normalized, _PROTEIN_TERMS):
        tags.add("protein")
    if food_group == "meat_eggs_dairy" and _contains(normalized, _DAIRY_TERMS):
        tags.add("dairy")
    return tags


def is_food_review_query(text: str) -> bool:
    normalized = _normalize(text)
    return any(re.search(pattern, normalized) for pattern in _REVIEW_PATTERNS)


def _number_value(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    simple = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if text in simple:
        return simple[text]
    match = re.fullmatch(r"([一二两三四五六七八九])?十([一二三四五六七八九])?", text)
    if match:
        return (simple.get(match.group(1), 1) * 10) + simple.get(match.group(2), 0)
    if text in {"一个", "一個"}:
        return 1
    if text in {"半", "半个", "半個"}:
        return 1
    return None


def _subtract_months(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def resolve_food_review_period(text: str, today: date) -> tuple[date, date]:
    """Resolve explicit dates/relative periods; default to the last 20 calendar days."""
    date_pattern = r"(?<!\d)(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?(?!\d)"
    found: list[date] = []
    for match in re.finditer(date_pattern, text):
        found.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    if len(found) >= 2:
        start, end = found[0], found[1]
    elif len(found) == 1:
        start = end = found[0]
    elif "上个月" in text or "上月" in text or "先月" in text:
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
    elif "本月" in text or "这个月" in text or "今月" in text:
        start, end = today.replace(day=1), today
    elif "上周" in text or "上星期" in text or "先週" in text:
        this_monday = today - timedelta(days=today.weekday())
        end = this_monday - timedelta(days=1)
        start = end - timedelta(days=6)
    elif "本周" in text or "这周" in text or "本星期" in text or "今週" in text:
        start, end = today - timedelta(days=today.weekday()), today
    elif "昨天" in text or "昨日" in text:
        start = end = today - timedelta(days=1)
    elif "今天" in text or "今日" in text:
        start = end = today
    else:
        duration = re.search(
            r"(?:近|最近|过去|過去|過去的|最近的)\s*(一个月|一個月|半个月|半個月|[一二两三四五六七八九十\d]+)\s*(天|日|周|星期|礼拜|個月|个月|月)",
            text,
        )
        if duration:
            count_text, unit = duration.groups()
            if "半个月" in count_text or "半個月" in count_text:
                start = today - timedelta(days=14)
            elif "月" in unit:
                count = 1 if count_text in {"一个月", "一個月"} else _number_value(count_text)
                if count is None:
                    raise ValueError("无法识别查询的月份范围，请使用明确日期或天数。")
                start = _subtract_months(today, count)
            else:
                count = _number_value(count_text)
                if count is None or count < 1:
                    raise ValueError("无法识别查询的时间范围，请使用明确日期或天数。")
                days = count * (7 if unit in {"周", "星期", "礼拜"} else 1)
                start = today - timedelta(days=days - 1)
            end = today
        else:
            start, end = today - timedelta(days=19), today
    if start > end:
        raise ValueError("查询开始日期晚于结束日期，请检查日期范围。")
    if end > today:
        end = today
    if start > end:
        raise ValueError("所选日期范围在未来，没有可回顾的饮食记录。")
    return start, end


def build_food_review_answer(database: Any, text: str, today: date) -> str:
    try:
        start, end = resolve_food_review_period(text, today)
    except ValueError as exc:
        return str(exc)
    days_in_range = (end - start).days + 1
    consumption_rows = database.connection.execute(
        """SELECT consumed_on,meal,item_name,quantity_text,note
           FROM food_consumption_records
           WHERE consumed_on BETWEEN ? AND ?
           ORDER BY consumed_on,meal,id""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    count_purchases = database.get_setting(PURCHASES_AS_EATEN_SETTING, "0") == "1"
    purchase_rows = database.connection.execute(
        """SELECT purchase_date,item_name,quantity_text,food_group
           FROM food_purchase_items
           WHERE purchase_date BETWEEN ? AND ?
           ORDER BY purchase_date,item_name,id""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    manual_keys = {
        (str(row["consumed_on"]), _normalize(str(row["item_name"]).strip()))
        for row in consumption_rows
    }
    counted_purchases = [
        row for row in purchase_rows
        if count_purchases
        and str(row["food_group"]) in FOOD_GROUP_TO_CLASSIFICATION
        and str(row["food_group"]) not in {"other", "unclassified"}
        and (str(row["purchase_date"]), _normalize(str(row["item_name"]).strip())) not in manual_keys
    ]
    records: list[dict[str, Any]] = [
        {
            "date": str(row["consumed_on"]),
            "meal": str(row["meal"] or "").strip(),
            "item": str(row["item_name"]),
            "quantity": str(row["quantity_text"] or "").strip(),
            "note": str(row["note"] or "").strip(),
            "food_group": None,
            "source": "食用记录",
        }
        for row in consumption_rows
    ]
    records.extend(
        {
            "date": str(row["purchase_date"]),
            "meal": "",
            "item": str(row["item_name"]),
            "quantity": str(row["quantity_text"] or "").strip(),
            "note": "",
            "food_group": str(row["food_group"]),
            "source": "按偏好从采购记录计入已吃",
        }
        for row in counted_purchases
    )
    records.sort(key=lambda row: (row["date"], row["meal"], row["item"]))
    lines = [
        f"饮食记录回顾：{start.isoformat()} 至 {end.isoformat()}（{days_in_range}天）",
        (
            f"食用日志 {len(consumption_rows)} 条"
            + (f"；按设置把 {len(counted_purchases)} 条已分类食品采购计作已吃" if count_purchases else "")
            + f"；共计 {len(records)} 条，覆盖 {len({row['date'] for row in records})}/{days_in_range} 天。"
        ),
    ]
    if not records:
        if count_purchases:
            lines.append("这段时间没有食用日志，也没有已分类食品采购可计入饮食回顾。")
        else:
            lines.append("这段时间没有找到已保存的食用记录。采购清单只代表买过，不会自动计作已吃。")
        if purchase_rows:
            by_purchase_date: dict[str, list[str]] = defaultdict(list)
            for row in purchase_rows:
                item = str(row["item_name"])
                quantity = str(row["quantity_text"] or "").strip()
                group = FOOD_GROUP_LABELS.get(str(row["food_group"]), "待识别")
                entry = f"{item}（{group}）" + (f"，{quantity}" if quantity else "")
                by_purchase_date[str(row["purchase_date"])].append(entry)
            heading = "未计入饮食回顾的采购商品" if count_purchases else "同期采购商品记录（只表示买过）"
            lines.append(f"{heading}：")
            for day, entries in by_purchase_date.items():
                lines.append(f"- {day}：" + "；".join(entries))
            if count_purchases:
                lines.append("“其他商品”和“待识别”商品均未计作已吃，也不参加营养类别统计。")
            else:
                lines.append("以上采购商品没有计入已吃食物或营养覆盖。")
        lines.append("目前没有可用于评估饮食类别覆盖的食品记录。")
        return "\n".join(lines)

    by_date: dict[str, list[str]] = defaultdict(list)
    category_days: dict[str, set[str]] = {key: set() for key, _, _ in _GROUPS}
    no_nutrition_tag: list[str] = []
    for row in records:
        item = row["item"]
        quantity = row["quantity"]
        meal = row["meal"]
        note = row["note"]
        entry = item + (f"（{quantity}）" if quantity else "")
        if row["source"] != "食用记录":
            group_label = FOOD_GROUP_LABELS.get(row["food_group"], "食品")
            entry += f"（按采购计入已吃·{group_label}）"
        if note:
            entry += f"；备注：{note}"
        by_date[row["date"]].append(f"{meal + '：' if meal else ''}{entry}")
        tags = _nutrition_tags(item, row["food_group"])
        if not tags:
            no_nutrition_tag.append(item)
        for tag in tags:
            category_days[tag].add(row["date"])

    lines.append("按日期汇总的食物：")
    for day, entries in by_date.items():
        lines.append(f"- {day}：" + "；".join(entries))

    coverage = [(key, label, recommendation, len(category_days[key])) for key, label, recommendation in _GROUPS]
    lines.append("\n按食物名称识别的类别覆盖（有记录的天数）：")
    for _key, label, _recommendation, count in coverage:
        lines.append(f"- {label}：{count}/{days_in_range} 天")

    recognized_days = max((count for _key, _label, _rec, count in coverage), default=0)
    if recognized_days == 0:
        lines.append("\n这些名称无法可靠归入主食、蔬菜、水果、蛋白质来源或奶类，暂时不能给出有依据的类别覆盖建议。")
    else:
        least_count = min(count for _key, _label, _rec, count in coverage)
        least_groups = [group for group in coverage if group[3] == least_count]
        if least_count == recognized_days:
            lines.append("\n这五类在现有记录中的出现天数相近；记录覆盖率和数量信息不足以判断哪类摄入不足。")
        else:
            if least_count == 0:
                lines.append("\n日志里未记录到以下类别；这表示没有日志证据，不能证明你实际没有吃或身体缺乏：")
            else:
                lines.append("\n以下类别在现有五类中记录天数最少；这是日志覆盖比较，不是营养缺乏诊断：")
            for _key, label, recommendation, count in least_groups:
                if count == 0:
                    lines.append(f"- {label}（0/{days_in_range}天）：可考虑加入{recommendation}。")
                else:
                    lines.append(f"- {label}（{count}/{days_in_range}天）：可考虑增加{recommendation}的种类。")

    if no_nutrition_tag:
        names = "、".join(dict.fromkeys(no_nutrition_tag))
        lines.append(f"\n未纳入五类营养覆盖统计的名称：{names}。可能是饮料、零食、复合食品或待识别商品。")
    lines.append(
        "\n说明：按日期列出食用日志；"
        + ("已按你的设置把已分类食品采购计作已吃；“其他商品”和“待识别”均不计入。" if count_purchases else "采购记录未计作摄入。")
        + "食物名称和天数不能说明份量、烹调方式、吸收情况或化验指标。"
        "因此这里仅提示日志中未记录或较少记录的食物类别，不能据此判断维生素、矿物质等具体缺乏。"
        "结果使用日本厚生劳动省食事バランスガイド的主食、主菜、副菜、乳制品和水果分类作饮食多样性参考，不计算份数或营养素。"
    )
    return "\n".join(lines)
