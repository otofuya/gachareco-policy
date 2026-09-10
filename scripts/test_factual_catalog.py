import copy
import json
import tempfile
import unittest
from pathlib import Path
from factual_catalog import facts, publish
from scrape_catalog import extract_price, create_session, scrape_listing_page, stable_items, fetch_detail_batch
from datetime import datetime, timezone
from scrape_catalog import parse_detail_facts, detail_targets, merge_entries, preserve_verified_details
from unittest.mock import patch, Mock
import requests


class FactsTest(unittest.TestCase):
    def setUp(self):
        self.raw = {'version': 1, 'series': [{'id': 's', 'name': 's', 'accentColor': '#123456'}],
                    'gachas': [{'id': 'gi-1', 'title': '商品', 'seriesId': 's', 'seriesName': 's',
                    'maker': 'm', 'price': 300, 'release': '', 'category': 'gacha',
                    'items': [], 'imageUrl': 'https://example.com/a.jpg', 'description': 'not facts'}]}

    def test_allowlist_and_unknown(self):
        row = facts(self.raw)['gachas'][0]
        self.assertNotIn('imageUrl', row)
        self.assertNotIn('description', row)
        self.assertFalse(row['priceKnown'])
        self.assertIsNone(row['totalTypes'])

    def test_invalid_update_preserves_file(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'facts.json'
            publish(self.raw, target)
            before = target.read_bytes()
            for rows in [[], self.raw['gachas']*2]:
                bad = copy.deepcopy(self.raw)
                bad['gachas'] = rows
                with self.assertRaises(ValueError): publish(bad, target)
                self.assertEqual(before, target.read_bytes())

    def test_no_price_guess_or_set_conversion(self):
        self.assertEqual(extract_price('未定'), 0)
        self.assertEqual(extract_price('全種セット 2000円'), 0)
        self.assertEqual(extract_price('500円 全5種'), 500)
        self.assertEqual(extract_price('全500種'), 0)

    def test_names_update_without_reassigning_existing_ids(self):
        entry = {'id': 'gi-1', 'items': [
            {'id': 'old-a', 'name': 'A'}, {'id': 'old-b', 'name': 'B'},
            {'id': 'old-c', 'name': '種類未確認'},
        ]}
        result = stable_items(entry, ['B', 'C', 'A'])
        self.assertEqual([(r['id'], r['name']) for r in result], [('old-a', 'A'), ('old-b', 'B'), ('old-c', 'C')])

    def test_popular_tab_is_not_collected(self):
        html = '''<div id="post_list_tab_1"><li class="p-postList__item">
          <a class="p-postList__link" href="https://gacha-island.jp/1/">link</a>
          <h2 class="p-postList__title">テスト商品</h2></li></div>
          <div id="post_list_tab_2"><li class="p-postList__item">
          <a class="p-postList__link" href="https://gacha-island.jp/2/">link</a>
          <h2 class="p-postList__title">人気の商品</h2></li></div>'''
        response = Mock(text=html)
        rows = scrape_listing_page(Mock(get=Mock(return_value=response)), 1)
        self.assertEqual([r['id'] for r in rows], ['gi-1'])
        self.assertFalse(rows[0]['priceKnown'])
        self.assertIsNone(rows[0]['totalTypes'])

    def test_http_failure_aborts_and_throttles(self):
        for status in [403, 429, 500]:
            response = requests.Response()
            response.status_code = status
            with patch.object(requests.Session, 'get', return_value=response), patch('scrape_catalog.time.sleep') as sleep:
                session = create_session()
                session.last_request = __import__('time').monotonic()
                with self.assertRaises(requests.HTTPError): scrape_listing_page(session, 1)
                self.assertGreater(sleep.call_args.args[0], 1.9)

    def test_detail_batch_stops_on_first_error(self):
        rows = [{'id': f'gi-{n}', '_detailUrl': f'https://gacha-island.jp/{n}/', 'items': []} for n in range(3)]
        with patch('scrape_catalog.scrape_detail_facts', side_effect=requests.HTTPError('429')) as fetch:
            with self.assertRaises(requests.HTTPError): fetch_detail_batch(Mock(), rows)
            self.assertEqual(fetch.call_count, 1)

    def test_removed_product_retains_facts_without_blocking_others(self):
        response = requests.Response()
        response.status_code = 404
        rows = [dict(id='gi-1', _detailUrl='https://gacha-island.jp/1/', items=[], price=500, priceKnown=True),
                dict(id='gi-2', _detailUrl='https://gacha-island.jp/2/', items=[], price=300, priceKnown=True)]
        with patch('scrape_catalog.scrape_detail_facts', side_effect=[requests.HTTPError(response=response), {'price': 400, 'priceKnown': True}]):
            fetch_detail_batch(Mock(), rows)
        self.assertEqual([r['price'] for r in rows], [500, 400])

    def test_detail_checks_rotate_even_when_names_are_missing(self):
        checked = {'id': 'gi-1', '_detailUrl': 'https://gacha-island.jp/1/', 'items': [], 'factsCheckedAt': '2026-09-09'}
        fresh = {'id': 'gi-2', '_detailUrl': 'https://gacha-island.jp/2/', 'items': []}
        with patch('scrape_catalog.scrape_detail_facts', return_value={}) as fetch:
            fetch_detail_batch(Mock(), [checked, fresh], limit=1)
            self.assertEqual(fetch.call_args.args[1], fresh['_detailUrl'])
            self.assertTrue(fresh.get('itemNamesCheckedAt'))

    def test_legacy_notes_are_not_product_variant_names(self):
        item = {'id': 'legacy-item', 'name': '※ランダムアソート', 'topColor': '#123456', 'bottomColor': '#123456', 'charColor': '#123456'}
        self.raw['gachas'][0]['items'] = [item]
        result = facts(self.raw)['gachas'][0]['items'][0]
        self.assertEqual(result['id'], 'legacy-item')
        self.assertEqual(result['name'], '種類未確認')


class DetailFactsTest(unittest.TestCase):
    def test_labelled_price_names_and_no_prose(self):
        result = parse_detail_facts("""<div class="gacha-spec-item"><h4>価格</h4><p>1回500円</p></div>
        <div class="gacha-spec-item"><h4>発売日</h4><p>2026年9月</p></div>
        <div class="gacha-spec-item"><h4>商品内容</h4><p>・<span>赤</span>いねこ<br>・白いねこ<br>※注意</p></div>
        <img src="no.jpg"><p>紹介文</p>""")
        self.assertEqual(result, {'price': 500, 'priceKnown': True, 'priceStatus': 'known', 'release': '2026.09', 'releaseStatus': 'known', 'names': ['赤いねこ', '白いねこ']})

    def test_unknown_price_is_not_fabricated(self):
        self.assertEqual(parse_detail_facts('<div class="gacha-spec-item"><h4>価格</h4><p>※価格未定</p></div>'), {'price': 0, 'priceKnown': False, 'priceStatus': 'pending', '_priceVerified': True})

    def test_title_and_explicit_pending_in_article_are_facts(self):
        parsed = parse_detail_facts('<h1 class="gacha-product-title"> 正しい 商品名 </h1><div class="gacha-spec-item"><h4>メーカー</h4><p>メーカー</p></div><div class="post_content"><p>※発売日未定、価格未定</p><div><p>他の商品紹介文</p></div></div>')
        self.assertEqual(parsed['title'], '正しい 商品名')
        self.assertEqual(parsed['priceStatus'], 'pending')
        self.assertEqual(parsed['releaseStatus'], 'pending')
        row = dict(id='gi-1', title='古い名前', price=500, priceKnown=True, release='2026.09', items=[])
        merge_entries({'gachas': [row], 'series': []}, [{'id': 'gi-1', **parsed, 'items': []}])
        self.assertEqual((row['title'], row['priceKnown'], row['release']), ('正しい 商品名', False, ''))

    def test_related_product_pending_does_not_override_current_product(self):
        parsed = parse_detail_facts('<div class="gacha-spec-item"><h4>価格</h4><p>500円</p></div><div class="post_content"><div><p>※発売日未定、価格未定</p></div></div>')
        self.assertTrue(parsed['priceKnown'])
        self.assertNotIn('releaseStatus', parsed)

    def test_listing_cannot_turn_verified_pending_price_into_known_price(self):
        previous = dict(factsCheckedAt='2026-09-10', title='詳細の名前', price=0, priceKnown=False, priceStatus='pending', release='', releaseStatus='pending')
        listing = dict(title='一覧の古い名前', price=500, priceKnown=True, release='2026.09')
        preserve_verified_details(listing, previous)
        self.assertEqual((listing['title'], listing['priceKnown'], listing['release']), ('詳細の名前', False, ''))

    def test_old_name_only_checks_do_not_skip_full_fact_verification(self):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        rows = [dict(id='gi-1', release='2026.09', priceKnown=True, itemNamesCheckedAt=now.isoformat())]
        self.assertEqual(detail_targets(rows, now), rows)

    def test_due_queue_revisits_unknown_prices_after_release(self):
        rows = [dict(id='gi-1', release='2026.10', priceKnown=False, factsCheckedAt='2026-09-30T00:00:00+00:00'),
                dict(id='gi-2', release='2026.11', priceKnown=False, factsCheckedAt='2026-09-30T00:00:00+00:00'),
                dict(id='gi-3', release='2026.09', priceKnown=True, factsCheckedAt='2026-09-30T00:00:00+00:00')]
        due = detail_targets(rows, datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual([r['id'] for r in due], ['gi-1'])

    def test_listing_missing_price_does_not_erase_known_price(self):
        original = dict(id='gi-1', title='商品', price=500, priceKnown=True, items=[])
        catalog = {'gachas': [original], 'series': []}
        merge_entries(catalog, [dict(id='gi-1', title='商品', price=0, priceKnown=False, items=[])])
        self.assertEqual((original['price'], original['priceKnown']), (500, True))

if __name__ == '__main__': unittest.main()
