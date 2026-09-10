#!/usr/bin/env python3
"""
ガチャカタログ自動更新スクリプト
ガチャガチャアイランド（https://gacha-island.jp/products/）から全商品情報を取得し、
事実のみを docs/gacha-facts.json に出力する。旧カタログは変更しない。

requests + BeautifulSoup使用（JS不要のため高速）。
実行: python scripts/scrape_catalog.py [--detail-limit N] [--list-pages N]
"""

import argparse
import hashlib
import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse
from datetime import date, datetime, timezone
from factual_catalog import publish
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CATALOG_PATH = Path(__file__).parent.parent / "docs" / "gacha-catalog.json"
BASE_URL = "https://gacha-island.jp"
PRODUCTS_URL = f"{BASE_URL}/products/page"

DEFAULT_COLORS = [
    ("#ef4444", "#fca5a5"),
    ("#f97316", "#fdba74"),
    ("#eab308", "#fde047"),
    ("#22c55e", "#86efac"),
    ("#3b82f6", "#93c5fd"),
    ("#8b5cf6", "#c4b5fd"),
    ("#ec4899", "#f9a8d4"),
    ("#06b6d4", "#67e8f9"),
]

KNOWN_SERIES = {
    "ポケモン": ("pokemon", "ポケモン", "#f59e0b"),
    "ポケットモンスター": ("pokemon", "ポケモン", "#f59e0b"),
    "ちいかわ": ("chiikawa", "ちいかわ", "#f472b6"),
    "mofusand": ("mofusand", "mofusand", "#fb923c"),
    "モフサンド": ("mofusand", "mofusand", "#fb923c"),
    "たまごっち": ("tamagotchi", "たまごっち", "#a78bfa"),
    "ドラゴンボール": ("dragonball", "ドラゴンボール", "#f97316"),
    "ワンピース": ("onepiece", "ワンピース", "#ef4444"),
    "ONE PIECE": ("onepiece", "ワンピース", "#ef4444"),
    "鬼滅の刃": ("kimetsu", "鬼滅の刃", "#22c55e"),
    "呪術廻戦": ("jujutsu", "呪術廻戦", "#6366f1"),
    "すみっコぐらし": ("sumikko", "すみっコぐらし", "#86efac"),
    "サンリオ": ("sanrio", "サンリオ", "#f9a8d4"),
    "ディズニー": ("disney", "ディズニー", "#60a5fa"),
    "スプラトゥーン": ("splatoon", "スプラトゥーン", "#4ade80"),
    "スーパーマリオ": ("mario", "スーパーマリオ", "#ef4444"),
    "マリオ": ("mario", "スーパーマリオ", "#ef4444"),
    "星のカービィ": ("kirby", "星のカービィ", "#f472b6"),
    "カービィ": ("kirby", "星のカービィ", "#f472b6"),
    "クレヨンしんちゃん": ("shinchan", "クレヨンしんちゃん", "#fbbf24"),
    "SPY×FAMILY": ("spyfamily", "SPY×FAMILY", "#ef4444"),
    "スパイファミリー": ("spyfamily", "SPY×FAMILY", "#ef4444"),
    "推しの子": ("oshinoko", "推しの子", "#c084fc"),
    "シンカリオン": ("shinkalion", "シンカリオン", "#3b82f6"),
    "仮面ライダー": ("kamenrider", "仮面ライダー", "#22c55e"),
    "ウルトラマン": ("ultraman", "ウルトラマン", "#ef4444"),
    "ガンダム": ("gundam", "ガンダム", "#6366f1"),
    "プリキュア": ("precure", "プリキュア", "#f472b6"),
    "トイ・ストーリー": ("toystory", "トイ・ストーリー", "#60a5fa"),
    "ミニオン": ("minions", "ミニオン", "#fbbf24"),
    "どうぶつの森": ("animalcrossing", "どうぶつの森", "#4ade80"),
    "ハイキュー": ("haikyu", "ハイキュー!!", "#f97316"),
    "チェンソーマン": ("chainsawman", "チェンソーマン", "#ef4444"),
    "僕のヒーローアカデミア": ("heroaca", "僕のヒーローアカデミア", "#22c55e"),
    "ヒロアカ": ("heroaca", "僕のヒーローアカデミア", "#22c55e"),
    "名探偵コナン": ("conan", "名探偵コナン", "#3b82f6"),
    "コナン": ("conan", "名探偵コナン", "#3b82f6"),
    "アンパンマン": ("anpanman", "アンパンマン", "#f97316"),
    "ドラえもん": ("doraemon", "ドラえもん", "#3b82f6"),
    "クロミ": ("sanrio", "サンリオ", "#f9a8d4"),
    "シナモロール": ("sanrio", "サンリオ", "#f9a8d4"),
    "マイメロディ": ("sanrio", "サンリオ", "#f9a8d4"),
    "リラックマ": ("rilakkuma", "リラックマ", "#fbbf24"),
    "ミッフィー": ("miffy", "ミッフィー", "#f97316"),
    "スヌーピー": ("snoopy", "スヌーピー", "#fbbf24"),
    "PEANUTS": ("snoopy", "スヌーピー", "#fbbf24"),
    "トムとジェリー": ("tomandjerry", "トムとジェリー", "#8b5cf6"),
    "ムーミン": ("moomin", "ムーミン", "#06b6d4"),
    "コウペンちゃん": ("koupen", "コウペンちゃん", "#86efac"),
    "にゃんこ大戦争": ("nyanko", "にゃんこ大戦争", "#ef4444"),
    "ブルーロック": ("bluelock", "ブルーロック", "#3b82f6"),
    "東京リベンジャーズ": ("tokyorev", "東京リベンジャーズ", "#6366f1"),
    "葬送のフリーレン": ("frieren", "葬送のフリーレン", "#8b5cf6"),
    "フリーレン": ("frieren", "葬送のフリーレン", "#8b5cf6"),
    "進撃の巨人": ("aot", "進撃の巨人", "#22c55e"),
    "ヒプノシスマイク": ("hypmic", "ヒプノシスマイク", "#6366f1"),
    "ツイステ": ("twisted", "ツイステッドワンダーランド", "#6366f1"),
    "ピクミン": ("pikmin", "ピクミン", "#ef4444"),
    "あつまれ": ("animalcrossing", "どうぶつの森", "#4ade80"),
    "NieR": ("nier", "NieR", "#6366f1"),
    "BEYBLADE": ("beyblade", "ベイブレード", "#3b82f6"),
    "ベイブレード": ("beyblade", "ベイブレード", "#3b82f6"),
    "トミカ": ("tomica", "トミカ", "#ef4444"),
    "プラレール": ("plarail", "プラレール", "#3b82f6"),
    "パンダの穴": ("pandanoana", "パンダの穴", "#22c55e"),
    "コップのフチ子": ("fuchiko", "コップのフチ子", "#f472b6"),
}

# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def load_catalog() -> dict:
    path = CATALOG_PATH.with_name("gacha-facts.json")
    if not path.exists(): path = CATALOG_PATH
    if not path.exists():
        return {"version": 0, "series": [], "gachas": [], "updatedAt": "", "lastChecked": ""}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog: dict) -> None:
    publish(catalog, CATALOG_PATH.with_name('gacha-facts.json'))


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def extract_price(text: str) -> int:
    if "セット" in text or "BOX" in text.upper():
        return 0
    nums = re.findall(r"(\d+)\s*円", text.replace(",", ""))
    for n in nums:
        val = int(n)
        if 0 < val <= 1000000:
            return val
    return 0


def extract_release(text: str) -> str:
    m = re.search(r"(\d{4})[年./\-](\d{1,2})", text)
    if m:
        if 1 <= int(m.group(2)) <= 12:
            return f"{m.group(1)}.{m.group(2).zfill(2)}"
    return ""


def detect_series(title: str, category_hint: str = "") -> tuple:
    for text in [category_hint, title]:
        for keyword, (sid, sname, color) in KNOWN_SERIES.items():
            if keyword in text:
                return sid, sname, color
    if category_hint and len(category_hint) >= 2:
        sid = stable_hash(category_hint)
        return sid, category_hint, "#6366f1"
    return "other", "その他", "#6366f1"


def make_items(gacha_id: str, names: list[str] | None = None, count: int = 0) -> list[dict]:
    if names:
        count = len(names)
    items = []
    for i in range(count):
        top, bottom = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        name = names[i] if names and i < len(names) else f"タイプ{i+1}"
        items.append({
            "id": f"{gacha_id}-{i}",
            "name": name,
            "topColor": top,
            "bottomColor": bottom,
            "charColor": top,
        })
    return items


def has_generic_items(gacha: dict) -> bool:
    for item in gacha.get("items", []):
        name = item.get("name", "")
        if name == '種類未確認' or re.match(r"^(アイテム|タイプ)\d+$", name):
            return True
    return not gacha.get("items")


def stable_items(entry: dict, names: list[str]) -> list[dict]:
    """Keep all previously published IDs. Resolve unnamed legacy slots in order."""
    old = entry.get('items', [])
    result = [dict(i) for i in old]
    existing_names = {i['name'] for i in result}
    available = [i for i in result if i['name'] == '種類未確認' or
                 re.fullmatch(r'(タイプ|アイテム)\s*\d+', i['name'])]
    used_ids = {i['id'] for i in result}
    for name in dict.fromkeys(names):
        if name in existing_names:
            continue
        if available:
            available.pop(0)['name'] = name
        else:
            index = len(result)
            while f"{entry['id']}-{index}" in used_ids:
                index += 1
            item = make_items(entry['id'], names=[name])[0]
            item['id'] = f"{entry['id']}-{index}"
            result.append(item)
            used_ids.add(item['id'])
        existing_names.add(name)
    return result


# ---------------------------------------------------------------------------
# HTTP セッション
# ---------------------------------------------------------------------------

def create_session() -> requests.Session:
    class ThrottledSession(requests.Session):
        last_request = 0.0
        def get(self, url, **kwargs):
            for _ in range(4):
                time.sleep(max(0, 2 - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                response = super().get(url, allow_redirects=False, **kwargs)
                response.raise_for_status()
                if not response.is_redirect:
                    return response
                destination = urljoin(url, response.headers['Location'])
                if urlparse(destination).netloc != urlparse(BASE_URL).netloc or urlparse(destination).scheme != 'https':
                    raise requests.HTTPError('Unexpected redirect', response=response)
                url = destination
            raise requests.HTTPError('Too many redirects')
    s = ThrottledSession()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    })
    return s


# ---------------------------------------------------------------------------
# 一覧ページスクレイピング
# ---------------------------------------------------------------------------

def get_total_pages(session: requests.Session) -> int:
    """ガチャガチャアイランドの全ページ数を取得"""
    r = session.get(f"{PRODUCTS_URL}/1/", timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    pag = soup.select_one("div.c-pagination")
    if not pag:
        return 1
    last_link = pag.select_one("a.-to-last")
    if last_link:
        m = re.search(r"/page/(\d+)", last_link.get("href", ""))
        if m:
            return int(m.group(1))
    page_nums = pag.select("a.page-numbers")
    if page_nums:
        nums = []
        for a in page_nums:
            txt = a.get_text(strip=True)
            if txt.isdigit():
                nums.append(int(txt))
        if nums:
            return max(nums)
    return 1


def extract_page_id(href: str) -> str | None:
    """商品URLからページIDを抽出: https://gacha-island.jp/50233/ → 50233"""
    m = re.search(r"gacha-island\.jp/(\d+)/?$", href)
    return m.group(1) if m else None


def scrape_listing_page(session: requests.Session, page_num: int) -> list[dict]:
    """一覧ページ1ページ分をスクレイピング"""
    url = f"{PRODUCTS_URL}/{page_num}/"
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  一覧ページ{page_num}取得失敗: {e}")
        raise

    soup = BeautifulSoup(r.text, "html.parser")
    listing = soup.select_one('#post_list_tab_1')
    if listing is None:
        raise ValueError('Product listing structure changed')
    cards = listing.select("li.p-postList__item")
    results = []

    for card in cards:
        try:
            link_el = card.select_one("a.p-postList__link[href]")
            if not link_el:
                continue
            href = link_el["href"]
            page_id = extract_page_id(href)
            if not page_id:
                continue

            title_el = card.select_one("h2.p-postList__title") or card.select_one("h3.p-postList__title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 3:
                continue

            cat_el = card.select_one("span.c-postThumb__cat")
            category_hint = cat_el.get_text(strip=True) if cat_el else ""
            sid, sname, _scolor = detect_series(title, category_hint)

            price = 0
            release = ""
            maker = ""
            item_count = 0

            info_table = card.select_one("table.gacha-info-table")
            if info_table:
                for row in info_table.select("tr"):
                    th = row.select_one("th")
                    td = row.select_one("td")
                    if not th or not td:
                        continue
                    label = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    if label == "発売":
                        release = extract_release(value)
                    elif "価格" in label:
                        price = extract_price(value)
                        m = re.search(r"全(\d+)種", value)
                        if m:
                            item_count = int(m.group(1))
                    elif label == "メーカー":
                        maker = value

            if not maker:
                maker = "不明"

            gacha_id = f"gi-{page_id}"

            results.append({
                "id": gacha_id,
                "seriesId": sid,
                "seriesName": sname,
                "title": title,
                "maker": maker,
                "price": price,
                "category": "gacha",
                "release": release or extract_release(""),
                "priceKnown": price > 0,
                "totalTypes": item_count or None,
                "sourceUrl": href,
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "_detailUrl": href,
                "_itemCount": item_count,
            })
        except Exception as e:
            print(f"  カード解析エラー: {e}")
            raise

    if not results:
        raise ValueError("Empty listing page")
    return results


def scrape_all_listings(session: requests.Session, max_pages: int | None = None) -> list[dict]:
    """全一覧ページをスクレイピング"""
    total = get_total_pages(session)
    if max_pages:
        total = min(total, max_pages)
    print(f"一覧ページ: 全{total}ページをスクレイピング中...")

    all_entries = []
    for page_num in range(1, total + 1):
        entries = scrape_listing_page(session, page_num)
        all_entries.extend(entries)
        if page_num % 10 == 0 or page_num == total:
            print(f"  {page_num}/{total}ページ完了 (累計{len(all_entries)}件)")
        time.sleep(0.3)

    print(f"一覧取得完了: {len(all_entries)}件")
    return all_entries


# ---------------------------------------------------------------------------
# 詳細ページスクレイピング（アイテム名取得）
# ---------------------------------------------------------------------------

def scrape_detail_items(session: requests.Session, detail_url: str) -> list[str] | None:
    """詳細ページから商品内容（アイテム名リスト）を取得"""
    try:
        r = session.get(detail_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for spec in soup.select("div.gacha-spec-item"):
            h4 = spec.select_one("h4")
            if h4 and "商品内容" in h4.get_text(strip=True):
                p = spec.select_one("p")
                if not p:
                    return None
                raw = p.decode_contents()
                parts = re.split(r"<br\s*/?>", raw)
                names = []
                for part in parts:
                    clean = BeautifulSoup(part, 'html.parser').get_text(' ', strip=True)
                    clean = clean.lstrip("・").strip()
                    if clean and len(clean) <= 100 and not re.match(r'^(※|注[意：:]|対象年齢|発売元|販売元|©|Copyright)', clean, re.I):
                        names.append(clean)
                return names if names else None
        return None
    except Exception:
        raise


def fetch_detail_batch(session: requests.Session, entries: list[dict],
                       limit: int | None = 200, workers: int = 1) -> int:
    """Sequential requests stop immediately on failure; oldest checks run first."""
    targets = sorted(entries, key=lambda e: (
        e.get('itemNamesCheckedAt') or '', 0 if has_generic_items(e) else 1))
    if limit is not None:
        targets = targets[:limit]
    if not targets:
        print("詳細取得対象なし")
        return 0

    print(f"詳細ページ: {len(targets)}件のアイテム名を取得中...")
    updated = 0
    done = 0

    for entry in targets:
        url = entry.get("_detailUrl")
        if not url:
            continue
        names = scrape_detail_items(session, url)
        entry['itemNamesCheckedAt'] = datetime.now(timezone.utc).isoformat()
        done += 1
        if names:
            entry["items"] = stable_items(entry, names)
            updated += 1
        if done % 100 == 0 or done == len(targets):
            print(f"  {done}/{len(targets)}完了 (アイテム名取得: {updated}件)")

    print(f"詳細取得完了: {updated}/{len(targets)}件でアイテム名取得")
    return updated


# ---------------------------------------------------------------------------
# マージ
# ---------------------------------------------------------------------------

def merge_entries(catalog: dict, new_entries: list[dict]) -> bool:
    """新しいエントリをカタログにマージ。変更があればTrueを返す"""
    existing = {g["id"]: g for g in catalog["gachas"]}
    changed = False
    added = 0
    items_updated = 0
    incoming_ids = [entry['id'] for entry in new_entries]
    if len(set(incoming_ids)) != len(incoming_ids):
        raise ValueError('Duplicate products in fetched pages')

    for entry in new_entries:
        gid = entry["id"]

        clean = {k: v for k, v in entry.items() if not k.startswith("_")}
        if "items" not in clean:
            clean["items"] = make_items(gid, count=entry.get("_itemCount", 0))

        if gid not in existing:
            catalog["gachas"].append(clean)
            existing[gid] = clean
            changed = True
            added += 1
        else:
            cur = existing[gid]
            for field in ('title', 'maker', 'release', 'price', 'priceKnown', 'totalTypes', 'sourceUrl', 'retrievedAt', 'itemNamesCheckedAt'):
                if field in clean and cur.get(field) != clean[field]:
                    cur[field] = clean[field]
                    changed = True
            if clean['items'] != cur.get('items', []):
                cur["items"] = clean["items"]
                items_updated += 1
                changed = True
            if not cur.get("release") and clean.get("release"):
                cur["release"] = clean["release"]
                changed = True

    existing_series_ids = {s["id"] for s in catalog["series"]}
    for entry in new_entries:
        sid = entry.get("seriesId")
        if sid and sid not in existing_series_ids:
            scolor = "#6366f1"
            for _, (ks, _, kc) in KNOWN_SERIES.items():
                if ks == sid:
                    scolor = kc
                    break
            catalog["series"].append({
                "id": sid,
                "name": entry.get("seriesName", sid),
                "accentColor": scolor,
            })
            existing_series_ids.add(sid)
            changed = True

    print(f"  新規追加: {added}, アイテム名更新: {items_updated}")
    return changed


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def detail_only_from_catalog(session: requests.Session, catalog: dict,
                              limit: int | None = 200, workers: int = 1) -> bool:
    """既存カタログのジェネリック名エントリに対して詳細ページからアイテム名を取得"""
    targets = [g for g in catalog['gachas'] if g['id'].startswith('gi-')]
    for g in targets:
        g['_detailUrl'] = f"{BASE_URL}/{g['id'][3:]}/"
    fetch_detail_batch(session, targets, limit=limit)
    return bool(targets) and limit != 0


def main():
    parser = argparse.ArgumentParser(description="ガチャカタログ更新")
    parser.add_argument("--list-pages", type=int, default=None,
                        help="一覧ページの最大ページ数（デフォルト: 全ページ）")
    parser.add_argument("--detail-limit", type=int, default=200,
                        help="詳細取得する商品数上限（デフォルト: 200）")
    parser.add_argument("--detail-workers", type=int, choices=[1], default=1,
                        help="互換用。逐次取得のみ対応")
    parser.add_argument("--skip-detail", action="store_true",
                        help="詳細ページの取得をスキップ")
    parser.add_argument("--detail-only", action="store_true",
                        help="一覧スクレイピングをスキップし既存カタログの詳細のみ取得")
    parser.add_argument("--clean", action="store_true",
                        help="既存のgi-*/bd-*エントリを削除してから実行")
    args = parser.parse_args()
    if args.detail_limit < 0 or (args.list_pages is not None and args.list_pages < 1):
        parser.error('Limits must be nonnegative; list pages must be positive')

    print("=== ガチャカタログ自動更新 ===")
    catalog = load_catalog()
    print(f"現在のカタログ: version={catalog['version']}, "
          f"シリーズ={len(catalog['series'])}, ガチャ={len(catalog['gachas'])}")

    if args.clean:
        before = len(catalog["gachas"])
        catalog["gachas"] = [g for g in catalog["gachas"]
                             if not g["id"].startswith(("gi-", "bd-"))]
        catalog["series"] = [s for s in catalog["series"]
                             if not re.match(r"^[0-9a-f]{8}$", s["id"])
                             and s["id"] != "other"]
        print(f"クリーン: {before} → {len(catalog['gachas'])}件")

    session = create_session()

    if args.detail_only:
        changed = detail_only_from_catalog(
            session, catalog,
            limit=args.detail_limit, workers=args.detail_workers)
    else:
        entries = scrape_all_listings(session, max_pages=args.list_pages)
        old = {g['id']: g for g in catalog['gachas']}
        for entry in entries:
            if entry['id'] in old:
                entry['items'] = old[entry['id']].get('items', [])
                entry['itemNamesCheckedAt'] = old[entry['id']].get('itemNamesCheckedAt')

        if not args.skip_detail:
            for entry in entries:
                if "items" not in entry:
                    entry["items"] = make_items(entry["id"], count=entry.get("_itemCount", 0))

            fetch_detail_batch(session, entries,
                               limit=args.detail_limit,
                               workers=args.detail_workers)

        changed = merge_entries(catalog, entries)

    if changed:
        catalog["version"] += 1

    catalog["lastChecked"] = date.today().isoformat()
    save_catalog(catalog)

    gi_count = sum(1 for g in catalog["gachas"] if g["id"].startswith("gi-"))
    bd_count = sum(1 for g in catalog["gachas"] if g["id"].startswith("bd-"))
    other_count = len(catalog["gachas"]) - gi_count - bd_count
    print(f"完了: gi={gi_count}, bd={bd_count}, other={other_count}, "
          f"シリーズ={len(catalog['series'])}")

    total_items = sum(len(g.get("items", [])) for g in catalog["gachas"])
    generic = sum(1 for g in catalog["gachas"] if has_generic_items(g))
    real = len(catalog["gachas"]) - generic
    print(f"アイテム: 合計{total_items}, 実名あり{real}件, ジェネリック{generic}件")

    print('FACTUAL_CATALOG_OK')


if __name__ == "__main__":
    main()
