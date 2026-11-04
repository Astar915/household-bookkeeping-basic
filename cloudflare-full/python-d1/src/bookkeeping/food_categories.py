from __future__ import annotations

import re
import unicodedata


FOOD_GROUP_LABELS = {
    "meat_eggs_dairy": "肉蛋奶",
    "vegetables_fruits": "蔬菜水果",
    "grains_staples": "主食粮食",
    "snacks": "零食点心",
    "seafood": "海鲜水产",
    "beverages": "饮料",
    "seasonings_dry_goods": "调味干货",
    "beans_tofu": "豆制品",
    "prepared_frozen": "熟食冷冻",
    "other": "其他商品",
    "unclassified": "待识别",
}
FOOD_GROUPS = tuple(FOOD_GROUP_LABELS)
FOOD_GROUP_TO_CLASSIFICATION = {
    group: "ingredient" for group in FOOD_GROUPS if group not in {"other", "unclassified"}
}
FOOD_GROUP_TO_CLASSIFICATION.update({"other": "other", "unclassified": "unclassified"})


# These are product-type clues, not a language model. Unknown names stay
# unclassified; receipt rows without a positive food clue are filtered out.
_NON_FOOD = (
    "レジ袋", "レジぶくろ", "買い物袋", "ビニール袋", "ポリ袋", "ごみ袋", "ゴミ袋",
    "ティッシュ", "トイレットペーパー", "キッチンペーパー", "食器用洗剤", "洗濯洗剤",
    "洗剤", "歯ブラシ", "スポンジ", "シャンプー", "台所用品", "日用品", "雑貨",
    "ケーブル", "電池", "乾電池", "アルカリ電池", "ステレオ", "充電器", "イヤホン",
    "塑料袋", "购物袋", "垃圾袋", "洗衣液", "洗洁精", "清洁剂", "纸巾", "卫生纸", "牙刷", "海绵", "洗发水", "日用品",
    "电缆", "数据线", "电池", "充电器", "耳机", "接线", "端子连接",
    "plastic bag", "shopping bag", "trash bag", "garbage bag", "detergent", "tissue",
    "toilet paper", "toothbrush", "sponge", "shampoo", "household goods", "cable", "battery",
    "alkaline battery", "stereo cable", "charger", "earphones",
)
_NON_FOOD_PLACEHOLDERS = {
    "その他", "そのほか", "その他商品", "その他の商品", "不明", "商品", "商品名不明",
    "其他", "其它", "其他商品", "其他项目", "未识别", "待识别", "未识别商品", "无商品名称",
    "other", "others", "misc", "miscellaneous", "unknown", "unknown item", "unidentified item",
}
_BEVERAGES = (
    "野菜生活", "コカ・コーラ", "コカコーラ", "ペプシ", "ペプシゼロ", "pepsi", "pepsizero", "pepsi zero", "pepsi-zero", "可乐", "果汁", "饮料", "豆浆", "绿茶", "红茶", "矿泉水", "碳酸水", "咖啡",
    "コーラ", "ジュース", "清涼飲料", "飲料", "inゼリー", "ウィダーインゼリー",
    "カロリーメイト ドリンク", "calorie mate drink",
    "ソフトドリンク", "お茶", "緑茶", "麦茶", "紅茶", "コーヒー", "水", "ミネラルウォーター",
    "炭酸水", "スポーツドリンク", "エナジードリンク", "豆乳", "ミルクティー", "飲み物",
    "juice", "cola", "soft drink", "beverage", "green tea", "black tea", "coffee",
    "mineral water", "sparkling water", "sports drink", "energy drink", "soy milk",
)
_SNACKS = (
    "零食", "点心", "饼干", "巧克力", "薯片", "糖果", "蛋糕", "冰淇淋", "スナック", "おやつ", "菓子", "お菓子", "スコーン", "クッキー", "ビスケット", "チョコ",
    "チョコレート", "キャンディ", "飴", "グミ", "せんべい", "米菓", "ポテトチップ",
    "クラッカー", "ケーキ", "ドーナツ", "プリン", "アイスクリーム", "さきいか", "するめ",
    "カロリーメイト", "calorie mate", "caloriemate", "カロリー メイト",
    "soyjoy", "soy joy", "ソイジョイ", "栄養バー", "エネルギーバー", "nutrition bar", "energy bar",
    "snack", "cookie", "biscuit", "chocolate", "candy", "chips", "cracker", "cake",
    "donut", "ice cream", "scone",
)
_SEASONINGS = (
    "调味料", "酱油", "食盐", "白糖", "醋", "食用油", "胡椒", "香料", "番茄酱", "沙拉酱", "味精", "干货",
    "ご飯がススム", "ご飯がすすむ", "炊き込みわかめ", "ふりかけ", "だし", "出汁", "醤油", "しょうゆ",
    "味噌", "みそ", "食用油", "オリーブオイル", "砂糖", "酢", "みりん", "ソース", "ケチャップ", "マヨネーズ",
    "ドレッシング", "香辛料", "スパイス", "カレー粉", "コンソメ", "調味料", "乾物", "乾燥",
    "のり", "海苔", "わかめ", "昆布", "ごま", "小麦粉", "片栗粉", "ジャム",
    "seasoning", "soy sauce", "miso", "vinegar", "sugar", "salt", "spice", "sauce",
    "ketchup", "mayonnaise", "dressing", "stock", "dried seaweed", "flour", "jam",
)
_MEAT_EGGS_DAIRY = (
    "牛肉", "猪肉", "羊肉", "鸡肉", "鸡胸肉", "鸡腿肉", "鸭肉", "鸡蛋", "牛奶", "低脂乳", "低脂牛奶", "低脂肪乳", "低脂肪牛奶", "酸奶", "奶酪", "黄油", "鲜奶油", "培根", "火腿",
    "豚肉", "鶏肉", "鶏むね", "鶏もも", "ひき肉", "挽肉", "ベーコン", "ハム", "ソーセージ",
    "卵", "たまご", "玉子", "鶏卵", "牛乳", "ミルク", "ヨーグルト", "チーズ", "バター", "生クリーム",
    "低脂肪乳", "低脂乳", "低脂肪牛乳", "低脂牛乳", "乳飲料", "乳製品", "肉類", "食肉", "beef", "pork", "chicken", "meat", "bacon", "ham", "sausage",
    "egg", "eggs", "milk", "low-fat milk", "low fat milk", "yogurt", "yoghurt", "cheese", "butter", "cream", "dairy",
)
_SEAFOOD = (
    "海鲜", "水产", "鱼肉", "三文鱼", "金枪鱼", "鲭鱼", "虾", "螃蟹", "蟹肉", "鱿鱼", "章鱼", "牡蛎", "扇贝", "蛤蜊", "生鱼片",
    "魚介", "魚", "鮮魚", "水産", "魚介類", "刺身", "まぐろ", "マグロ", "鮭", "さけ", "サケ", "さば", "サバ",
    "鯖", "あじ", "アジ", "ぶり", "ブリ", "たら", "タラ", "えび", "エビ", "海老", "かに", "カニ", "蟹",
    "たこ", "タコ", "いか", "イカ", "貝", "しらす", "明太子", "たらこ", "魚卵", "牡蠣", "かき", "ほたて",
    "seafood", "fish", "salmon", "tuna", "mackerel", "shrimp", "prawn", "crab", "squid", "octopus",
    "shellfish", "oyster", "scallop", "roe",
)
_VEGETABLES_FRUITS = (
    "蔬菜", "水果", "卷心菜", "白菜", "生菜", "菠菜", "西兰花", "黄瓜", "番茄", "西红柿", "胡萝卜", "洋葱", "土豆", "马铃薯", "红薯", "南瓜", "青椒", "蘑菇",
    "苹果", "橘子", "橙子", "香蕉", "葡萄", "草莓", "桃子", "梨", "猕猴桃", "柠檬", "牛油果", "西瓜", "香菇",
    "野菜", "青果", "果物", "フルーツ", "vegetable", "fruit", "produce",
    "キャベツ", "白菜", "レタス", "ほうれん草", "小松菜", "ブロッコリー", "きゅうり", "胡瓜", "トマト",
    "ミニトマト", "なす", "茄子", "大根", "人参", "にんじん", "玉ねぎ", "たまねぎ", "ねぎ", "長ねぎ",
    "じゃがいも", "ジャガイモ", "さつまいも", "かぼちゃ", "ピーマン", "パプリカ", "きのこ", "しいたけ",
    "りんご", "林檎", "みかん", "バナナ", "ぶどう", "葡萄", "いちご", "苺", "もも", "桃", "梨", "なし",
    "キウイ", "オレンジ", "レモン", "アボカド", "メロン", "すいか", "スイカ",
    "cabbage", "lettuce", "spinach", "broccoli", "cucumber", "tomato", "carrot", "onion", "potato",
    "pumpkin", "mushroom", "apple", "banana", "grape", "strawberry", "orange", "lemon", "avocado",
)
_PRODUCE_INDICATORS = (
    "蔬菜", "水果", "卷心菜", "白菜", "生菜", "菠菜", "西兰花", "黄瓜", "番茄", "西红柿", "胡萝卜", "洋葱", "土豆", "马铃薯", "红薯", "南瓜", "青椒", "蘑菇",
    "野菜", "青果", "果物", "フルーツ", "vegetable", "fruit", "produce",
)
_BEANS_TOFU = (
    "豆腐", "纳豆", "大豆", "毛豆", "豆制品", "豆类", "納豆", "なっとう", "枝豆", "えだまめ", "豆類", "豆製品", "油揚げ", "厚揚げ", "おから",
    "tofu", "natto", "soybean", "edamame", "beans", "bean curd",
)
_GRAINS_STAPLES = (
    "大米", "糙米", "米饭", "面包", "面条", "米粉", "燕麦", "麦片", "主食", "饺子皮", "お米", "白米", "玄米", "もち米", "ごはん", "パン", "食パン", "麺", "うどん", "そば", "蕎麦",
    "ラーメン", "パスタ", "スパゲッティ", "マカロニ", "シリアル", "オートミール", "餅", "もち", "主食",
    "rice", "bread", "noodle", "noodles", "udon", "soba", "ramen", "pasta", "cereal", "oatmeal",
)
_PREPARED_FROZEN = (
    "熟食", "便当", "冷冻食品", "冷冻饺子", "三明治", "寿司", "饭团", "弁当", "お弁当", "惣菜", "総菜", "冷凍食品", "冷凍餃子", "冷凍ピザ", "冷凍炒飯", "冷凍チャーハン",
    "たこ焼き", "たこ焼", "たこやき", "お好み焼き", "お好み焼", "焼きそば", "焼そば",
    "から揚げ", "唐揚げ", "コロッケ", "天ぷら", "焼き鳥", "サンドイッチ", "寿司", "おにぎり", "レトルト食品",
    "ready meal", "prepared food", "frozen food", "frozen dumpling", "bento", "sandwich", "sushi", "onigiri", "takoyaki", "okonomiyaki", "yakisoba",
)
_PREPARED_PRIORITY = (
    "たこ焼き", "たこ焼", "たこやき", "お好み焼き", "お好み焼", "焼きそば", "焼そば",
    "takoyaki", "okonomiyaki", "yakisoba",
)


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def _has_term(name: str, term: str) -> bool:
    normalized_term = _normalize(term)
    if normalized_term.isascii() and normalized_term.replace(" ", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", name) is not None
    return normalized_term in name


def classify_food_name(item_name: str) -> str:
    """Return a stable product group from multilingual product-name clues."""
    if not isinstance(item_name, str) or not item_name.strip():
        return "unclassified"
    name = _normalize(item_name)
    if name in {_normalize(value) for value in _NON_FOOD_PLACEHOLDERS}:
        return "other"
    # Battery-size labels such as 単3/単4 are common compact receipt names.
    if re.search(r"単\s*(?:[1-5]|[一二三四五])", name):
        return "other"
    if name in {"米", "rice"}:
        return "grains_staples"
    if any(_has_term(name, term) for term in ("ご飯がススム", "ご飯がすすむ", "炊き込みわかめ")):
        return "seasonings_dry_goods"
    ordered_groups = (
        ("other", _NON_FOOD),
        ("beverages", _BEVERAGES),
        ("snacks", _SNACKS),
        ("seasonings_dry_goods", _SEASONINGS),
        ("meat_eggs_dairy", _MEAT_EGGS_DAIRY),
        ("seafood", _SEAFOOD),
        ("vegetables_fruits", _VEGETABLES_FRUITS),
        ("beans_tofu", _BEANS_TOFU),
        ("grains_staples", _GRAINS_STAPLES),
        ("prepared_frozen", _PREPARED_FROZEN),
    )
    for group, terms in ordered_groups:
        if group == "meat_eggs_dairy" and any(_has_term(name, term) for term in _PREPARED_PRIORITY):
            return "prepared_frozen"
        if group == "vegetables_fruits":
            if any(_has_term(name, term) for term in _PRODUCE_INDICATORS):
                return group
            # A fruit or vegetable embedded in a longer branded product name
            # (for example, a flavored yogurt) is not enough to infer that the
            # purchased item is fresh produce.
            produce_terms = tuple(term for term in terms if term not in _PRODUCE_INDICATORS)
            if any(
                _has_term(name, term) and len(name.replace(" ", "")) <= len(_normalize(term)) + 4
                for term in produce_terms
            ):
                return group
            continue
        if any(_has_term(name, term) for term in terms):
            return group
    return "unclassified"


def is_confirmed_food_name(item_name: str) -> bool:
    """True only when the name has a positive food clue, not merely an unknown label."""
    return classify_food_name(item_name) not in {"other", "unclassified"}
