"""Private, account-local product category corrections and web lookup helpers."""
from __future__ import annotations

import html
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request
from datetime import datetime, timezone
from typing import Any, Callable


MEMORY_SETTING_KEY = "agent_product_category_memory_v1"
MAX_CATEGORY_MEMORIES = 200
MAX_RETRIEVAL_RECORDS = MAX_CATEGORY_MEMORIES * 2
MAX_SEARCH_RESPONSE_BYTES = 128 * 1024
WIKIPEDIA_LANGUAGES = {"zh", "ja", "en"}
HISTORY_LOOKUP_LIMIT = 80


def _normalize_product_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"(?:收据商品|商品名称|商品|消费|支出|记账|买了|购买|購入|買った|expense|purchase|receipt)", "", text)
    text = re.sub(r"(?:jpy|cny|usd|日元|円|人民币|美元|元|块钱|块)", "", text, flags=re.IGNORECASE)
    # A trailing bare number is usually the price in casual notes (for
    # example, "高原の詩 498"). Keep model numbers embedded in product names.
    text = re.sub(r"\s+\d+(?:[,.，.]\d+)?\s*$", "", text)
    # Preserve letters from every Unicode script (Kana, Cyrillic, Arabic,
    # Hangul, Devanagari, etc.). Restricting this to Latin/CJK made the RAG
    # silently discard most non-Chinese product names.
    return "".join(character for character in text if character.isalnum())


def _clean_candidate(
    value: Any,
    account_names: list[str] | None = None,
    amount: str | None = None,
) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    for name in account_names or []:
        if name:
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\d{1,4}[年/.-]\d{1,2}(?:[月/.-]\d{1,2}日?)?|"
        r"(?:花了|消费|消費|購入|買った|购买|买了|记一笔|记账|支出|expense|purchase|收据商品|商品名称)",
        " ", text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:[¥￥$]\s*\d[\d,.，]*|\d[\d,.，]*\s*(?:JPY|CNY|USD|日元|人民币|美元|円|元|块钱|块))",
        " ", text, flags=re.IGNORECASE,
    )
    if amount:
        amount_key = re.escape(str(amount).replace(",", "").replace("，", ""))
        text = re.sub(rf"(?<![\w]){amount_key}(?![\w])", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" ：:，,。.;；、")[:120]


def _alias_candidates(value: Any) -> list[str]:
    text = str(value or "").strip()[:240]
    if not text:
        return []
    parts = re.split(r"[;；|/、,，\n]", text)
    normalized = []
    for part in [text, *parts]:
        alias = _normalize_product_text(part)
        if len(alias) >= 2 and alias not in normalized:
            normalized.append(alias)
    return normalized[:12]


def remember_category_correction(
    database: Any,
    *,
    old_description: str,
    new_description: str,
    category_name: str,
    item_names: list[str] | None = None,
) -> None:
    """Save an account-local retrieval example after an explicit category edit."""
    category = str(category_name or "").strip()
    if not category:
        return
    aliases: list[str] = []
    for value in [old_description, new_description, *(item_names or [])]:
        for alias in _alias_candidates(value):
            if alias not in aliases:
                aliases.append(alias)
    aliases = [alias for alias in aliases if len(alias) >= 2][:12]
    if not aliases:
        return
    try:
        records = json.loads(database.get_setting(MEMORY_SETTING_KEY, "[]"))
    except (TypeError, ValueError):
        records = []
    if not isinstance(records, list):
        records = []
    existing = [row for row in records if isinstance(row, dict)]
    # Replace exact-alias examples when the user corrects them again.
    alias_set = set(aliases)
    existing = [row for row in existing if not alias_set.intersection(
        item for item in row.get("aliases", []) if isinstance(item, str)
    )]
    existing.insert(0, {
        "aliases": aliases,
        "category": category,
        "kind": "expense",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })
    database.set_setting(
        MEMORY_SETTING_KEY,
        json.dumps(existing[:MAX_CATEGORY_MEMORIES], ensure_ascii=False, separators=(",", ":")),
        "Agent product category corrections for this account",
    )


def retrieve_category_correction(database: Any, query_values: list[str]) -> str | None:
    """Prefer explicit corrections, then exact account-local learned examples."""
    try:
        records = json.loads(database.get_setting(MEMORY_SETTING_KEY, "[]"))
    except (TypeError, ValueError):
        return None
    if not isinstance(records, list):
        return None
    queries = list(dict.fromkeys(
        alias for value in query_values for alias in _alias_candidates(value)
    ))
    if not queries:
        return None
    exact_queries = set(queries)
    scored: list[tuple[int, float, str, str]] = []
    for row in records[:MAX_RETRIEVAL_RECORDS]:
        if not isinstance(row, dict) or row.get("kind") not in {
            "expense", "expense_history"
        }:
            continue
        category = str(row.get("category") or "").strip()
        aliases = row.get("aliases")
        if not category or not isinstance(aliases, list):
            continue
        normalized_aliases = {
            _normalize_product_text(alias) for alias in aliases
            if isinstance(alias, str) and len(_normalize_product_text(alias)) >= 2
        }
        score = 1.0 if normalized_aliases & exact_queries else 0.0
        if not score:
            for alias in normalized_aliases:
                if len(alias) < 3:
                    continue
                if any(
                    min(len(alias), len(query)) >= 3
                    and (alias in query or query in alias)
                    for query in queries
                ):
                    score = 0.94
                    break
        if score >= 0.88:
            # Legacy "expense" entries are explicit user corrections. Learned
            # transaction examples are useful too, but always rank lower.
            priority = 2 if row.get("kind") == "expense" else 1
            scored.append((priority, score, str(row.get("updatedAt") or ""), category))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][3]


def retrieve_transaction_category(
    database: Any,
    query_values: list[str],
    *,
    amount: str | None = None,
) -> str | None:
    """Match a product against this ledger's previously classified expenses.

    The query runs only for an unresolved expense, is bounded to 80 rows, and
    never sends any ledger data outside the current account.
    """
    try:
        account_names = [
            str(row["name"] or "") for row in database.selectable_account_rows()
        ]
        candidates = list(dict.fromkeys(
            candidate for value in query_values
            if (candidate := _clean_candidate(value, account_names, amount))
        ))[:8]
        candidates.sort(key=lambda value: len(_normalize_product_text(value)), reverse=True)
        patterns: list[tuple[str, str, bool]] = []
        for candidate in candidates:
            key = _normalize_product_text(candidate)
            if len(key) < 2:
                continue
            exact_only = len(key) < 4
            escaped = candidate.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            patterns.append((key, escaped, exact_only))
        if not patterns:
            return None

        conditions: list[str] = []
        params: list[str] = []
        for _key, escaped, exact_only in patterns:
            if exact_only:
                conditions.append("(t.description=? OR f.item_name=?)")
                params.extend([escaped, escaped])
            else:
                conditions.append(
                    r"(t.description LIKE ? ESCAPE '\' OR f.item_name LIKE ? ESCAPE '\')"
                )
                params.extend([f"%{escaped}%", f"%{escaped}%"])
        rows = database.connection.execute(
            "SELECT t.id AS transaction_id,t.description,c.name AS category_name,f.item_name "
            "FROM transactions t JOIN categories c ON c.id=t.category_id "
            "LEFT JOIN food_purchase_items f ON f.transaction_id=t.id "
            "WHERE t.kind='expense' AND t.balance_effect='posted' AND c.kind='expense' "
            "AND c.is_active=1 AND (" + " OR ".join(conditions) + ") "
            "ORDER BY t.id DESC LIMIT ?",
            (*params, HISTORY_LOOKUP_LIMIT),
        ).fetchall()
    except Exception:
        # Some older imported ledgers may have an incomplete optional table;
        # this retrieval is supplemental and must never block a transaction.
        return None

    scored: list[tuple[int, int, str]] = []
    for row in rows:
        description_key = _normalize_product_text(row["description"] or "")
        item_key = _normalize_product_text(row["item_name"] or "")
        category = str(row["category_name"] or "").strip()
        for query_key, _pattern, _exact_only in patterns:
            if not category or len(query_key) < 2:
                continue
            if query_key == item_key:
                score = 3
            elif query_key == description_key:
                score = 3
            elif len(query_key) >= 4 and (query_key in item_key or query_key in description_key):
                score = 2
            elif len(item_key) >= 4 and (item_key in query_key or description_key in query_key):
                score = 1
            else:
                continue
            scored.append((score, int(row["transaction_id"] or 0), category))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score = scored[0][0]
    best_categories = {category for score, _recency, category in scored if score == best_score}
    if len(best_categories) == 1:
        return next(iter(best_categories))
    # When exact past entries disagree, use the latest matching entry rather
    # than making the user classify the same item again.
    return scored[0][2]


def remember_expense_example(
    database: Any,
    *,
    description: str,
    category_name: str,
    item_names: list[str] | None = None,
) -> None:
    """Keep a compact account-local RAG example after a successful expense."""
    category = str(category_name or "").strip()
    aliases: list[str] = []
    for value in [description, *(item_names or [])]:
        for alias in _alias_candidates(value):
            if alias not in aliases:
                aliases.append(alias)
    aliases = aliases[:12]
    if not category or not aliases:
        return
    try:
        records = json.loads(database.get_setting(MEMORY_SETTING_KEY, "[]"))
    except (TypeError, ValueError):
        records = []
    if not isinstance(records, list):
        records = []
    alias_set = set(aliases)
    history = [
        row for row in records
        if isinstance(row, dict) and row.get("kind") == "expense_history"
        and not alias_set.intersection(
            alias for alias in row.get("aliases", []) if isinstance(alias, str)
        )
    ]
    corrections = [
        row for row in records
        if isinstance(row, dict) and row.get("kind") == "expense"
    ]
    history.insert(0, {
        "aliases": aliases,
        "category": category,
        "kind": "expense_history",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })
    database.set_setting(
        MEMORY_SETTING_KEY,
        json.dumps([*corrections[:MAX_CATEGORY_MEMORIES], *history[:MAX_CATEGORY_MEMORIES]],
                   ensure_ascii=False, separators=(",", ":")),
        "Account-local product category retrieval examples",
    )


class _DuckDuckGoResults(HTMLParser):
    """Extract only visible result titles/snippets from DDG's no-JS HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.div_depth = 0
        self.capture: str | None = None
        self.capture_tag = ""
        self.capture_depth = 0
        self.capture_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self.current is None and tag == "div" and classes.intersection({"result", "results_links"}):
            self.current = {"title": "", "snippet": ""}
            self.div_depth = 1
        elif self.current is not None and tag == "div":
            self.div_depth += 1

        if self.current is None:
            return
        if tag == "a" and "result__a" in classes:
            self.capture = "title"
            self.capture_tag = "a"
            self.capture_depth = 0
            self.capture_buffer = []
        elif tag == "a" and "result__snippet" in classes:
            self.capture = "snippet"
            self.capture_tag = "a"
            self.capture_depth = 0
            self.capture_buffer = []
        elif self.capture is not None and tag not in {"br", "img", "input", "meta", "link"}:
            self.capture_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.capture is not None:
            if tag == self.capture_tag and self.capture_depth == 0:
                text = _plain_snippet(" ".join(self.capture_buffer), 400)
                if self.current is not None and text:
                    self.current[self.capture] = text
                self.capture = None
                self.capture_tag = ""
                self.capture_buffer = []
            elif self.capture_depth > 0:
                self.capture_depth -= 1
        if self.current is not None and tag == "div":
            self.div_depth -= 1
            if self.div_depth <= 0:
                if self.current.get("title"):
                    self.rows.append(self.current)
                self.current = None
                self.div_depth = 0

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.capture_buffer.append(data)


def _read_external(opener: Callable[..., Any], request: Request) -> bytes | None:
    try:
        with opener(request, timeout=7) as response:
            if int(getattr(response, "status", 200)) != 200:
                return None
            raw = response.read(MAX_SEARCH_RESPONSE_BYTES + 1)
        return raw if len(raw) <= MAX_SEARCH_RESPONSE_BYTES else None
    except Exception as exc:
        if exc.__class__.__name__ == "ModelRequestRequired":
            raise
        return None


def _search_duckduckgo(product: str, opener: Callable[..., Any]) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": product})
    request = Request(url, headers={
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "HouseholdBookkeeping/1.0 (product category lookup)",
    })
    raw = _read_external(opener, request)
    if raw is None:
        return []
    try:
        parser = _DuckDuckGoResults()
        parser.feed(raw.decode("utf-8", errors="replace"))
    except Exception:
        return []
    results: list[dict[str, str]] = []
    for row in parser.rows[:4]:
        title = _plain_snippet(row.get("title"), 120)
        snippet = _plain_snippet(row.get("snippet"), 320)
        if not title:
            continue
        results.append({
            "title": title,
            "snippet": snippet,
            "url": "https://duckduckgo.com/",
            "source": "DuckDuckGo 网页搜索",
        })
    return results


def _search_open_food_facts(product: str, opener: Callable[..., Any]) -> list[dict[str, str]]:
    params = urlencode({
        "search_terms": product,
        "search_simple": "1",
        "action": "process",
        "json": "1",
        "page_size": "4",
        "fields": "product_name,brands,categories,categories_tags,labels",
    })
    request = Request(
        f"https://world.openfoodfacts.org/cgi/search.pl?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "HouseholdBookkeeping/1.0 (product category lookup)",
        },
    )
    raw = _read_external(opener, request)
    if raw is None:
        return []
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    products = payload.get("products", []) if isinstance(payload, dict) else []
    if not isinstance(products, list):
        return []
    results: list[dict[str, str]] = []
    for product_row in products[:4]:
        if not isinstance(product_row, dict):
            continue
        name = _plain_snippet(product_row.get("product_name"), 120)
        brands = _plain_snippet(product_row.get("brands"), 100)
        categories = product_row.get("categories")
        if not categories:
            categories = product_row.get("categories_tags")
        categories_text = _plain_snippet(categories, 260)
        labels = _plain_snippet(product_row.get("labels"), 140)
        title = " ".join(part for part in (name, brands) if part)
        snippet = "；".join(
            part for part in (
                f"商品类别：{categories_text}" if categories_text else "",
                f"标签：{labels}" if labels else "",
            ) if part
        )
        if not title or not snippet:
            continue
        results.append({
            "title": title,
            "snippet": snippet,
            "url": "https://world.openfoodfacts.org/",
            "source": "Open Food Facts 商品资料",
        })
    return results


def _plain_snippet(value: Any, limit: int = 500) -> str:
    text = html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def search_product_reference(
    query: str,
    *,
    response_language: str,
    opener: Callable[..., Any],
) -> list[dict[str, str]]:
    """Search free, bounded product references for one item in any language.

    Only the supplied product/brand query is sent. Account, amount, date, and
    ledger context are never included. The opener is Workflow-replayable on web.
    """
    product = re.sub(r"\s+", " ", str(query or "")).strip()[:96]
    if len(_normalize_product_text(product)) < 2:
        return []
    results = _search_duckduckgo(product, opener)
    # Product-name search is broad and multilingual; Open Food Facts adds
    # structured product/category data when the item is food or a drink.
    results.extend(_search_open_food_facts(product, opener))

    primary = {"ja-JP": "ja", "en-US": "en"}.get(response_language, "zh")
    order = [primary, "ja" if primary != "ja" else "zh", "en"]
    languages = list(dict.fromkeys(language for language in order if language in WIKIPEDIA_LANGUAGES))
    # One encyclopedia fallback only when both broader sources are empty, so a
    # failed lookup stays bounded to three external requests total.
    for language in (languages[:1] if not results else []):
        params = urlencode({
            "action": "query", "list": "search", "srsearch": product,
            "srwhat": "text", "srprop": "snippet", "srlimit": "3",
            "format": "json", "utf8": "1",
        })
        url = f"https://{language}.wikipedia.org/w/api.php?{params}"
        request = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "HouseholdBookkeeping/1.0 (product category reference)",
        })
        try:
            raw = _read_external(opener, request)
            if raw is None:
                continue
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            # Workflow's replay signal must escape so it can persist and replay
            # the external call. Other lookup failures fail closed to clarify.
            if exc.__class__.__name__ == "ModelRequestRequired":
                raise
            continue
        search_rows = payload.get("query", {}).get("search", []) if isinstance(payload, dict) else []
        wikipedia_results: list[dict[str, str]] = []
        for row in (search_rows[:3] if isinstance(search_rows, list) else []):
            if not isinstance(row, dict):
                continue
            title = _plain_snippet(row.get("title"), 120)
            snippet = _plain_snippet(row.get("snippet"), 320)
            page_id = row.get("pageid")
            if not title or not snippet or not isinstance(page_id, int):
                continue
            wikipedia_results.append({
                "title": title,
                "snippet": snippet,
                "url": f"https://{language}.wikipedia.org/?curid={page_id}",
                "source": f"{language}.wikipedia.org",
            })
        if wikipedia_results:
            results.extend(wikipedia_results)
            break

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in results:
        title = _plain_snippet(row.get("title"), 120)
        snippet = _plain_snippet(row.get("snippet"), 320)
        key = (_normalize_product_text(title), _normalize_product_text(snippet))
        if not title or key in seen:
            continue
        seen.add(key)
        unique.append({
            "title": title,
            "snippet": snippet,
            "url": str(row.get("url") or "")[:500],
            "source": str(row.get("source") or "网页搜索")[:80],
        })
        if len(unique) >= 8:
            break
    return unique
