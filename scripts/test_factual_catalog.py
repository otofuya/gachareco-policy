import copy
import json
import tempfile
import unittest
from pathlib import Path
from factual_catalog import facts, publish
from scrape_catalog import extract_price, create_session, scrape_listing_page, stable_items, fetch_detail_batch
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
        with patch('scrape_catalog.scrape_detail_items', side_effect=requests.HTTPError('429')) as fetch:
            with self.assertRaises(requests.HTTPError): fetch_detail_batch(Mock(), rows)
            self.assertEqual(fetch.call_count, 1)

    def test_detail_checks_rotate_even_when_names_are_missing(self):
        checked = {'id': 'gi-1', '_detailUrl': 'https://gacha-island.jp/1/', 'items': [], 'itemNamesCheckedAt': '2026-09-09'}
        fresh = {'id': 'gi-2', '_detailUrl': 'https://gacha-island.jp/2/', 'items': []}
        with patch('scrape_catalog.scrape_detail_items', return_value=None) as fetch:
            fetch_detail_batch(Mock(), [checked, fresh], limit=1)
            self.assertEqual(fetch.call_args.args[1], fresh['_detailUrl'])
            self.assertTrue(fresh.get('itemNamesCheckedAt'))

    def test_legacy_notes_are_not_product_variant_names(self):
        item = {'id': 'legacy-item', 'name': '※ランダムアソート', 'topColor': '#123456', 'bottomColor': '#123456', 'charColor': '#123456'}
        self.raw['gachas'][0]['items'] = [item]
        result = facts(self.raw)['gachas'][0]['items'][0]
        self.assertEqual(result['id'], 'legacy-item')
        self.assertEqual(result['name'], '種類未確認')


if __name__ == '__main__': unittest.main()
