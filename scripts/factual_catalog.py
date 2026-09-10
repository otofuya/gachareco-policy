"""Image-free delivery boundary. Legacy inputs remain untouched."""
import json
import re
from pathlib import Path

FIELDS = ('id', 'seriesId', 'seriesName', 'title', 'maker', 'price', 'category',
          'release', 'sourceUrl', 'retrievedAt', 'totalTypes', 'itemNamesCheckedAt',
          'factsCheckedAt', 'priceStatus', 'releaseStatus')
ITEM_FIELDS = ('id', 'name', 'topColor', 'bottomColor', 'charColor')


def facts(raw):
    rows = []
    ids, item_ids = set(), set()
    for source in raw['gachas']:
        row = {k: source[k] for k in FIELDS if k in source}
        if not row.get('id') or row['id'] in ids or not row.get('title'):
            raise ValueError('Missing/duplicate product')
        ids.add(row['id'])
        row['title'] = ' '.join(row['title'].split())
        row['priceKnown'] = source.get('priceKnown', False)
        for field in ('priceStatus', 'releaseStatus'):
            if field in row and row[field] not in ('known', 'pending'):
                raise ValueError('Invalid fact status')
        row['catalogFacts'] = True
        row['price'] = row.get('price') or 0
        if type(row['price']) is not int or not 0 <= row['price'] <= 1000000:
            raise ValueError('Invalid price')
        if type(row['priceKnown']) is not bool:
            raise ValueError('Invalid priceKnown')
        # Legacy scraper used guessed defaults; retain IDs but not their claims.
        row['items'] = []
        for item in source.get('items', []):
            if item['id'] in item_ids:
                raise ValueError('Duplicate item')
            item_ids.add(item['id'])
            clean = {k: item[k] for k in ITEM_FIELDS}
            if not clean['id'] or not isinstance(clean['name'], str):
                raise ValueError('Invalid item')
            clean['name'] = ' '.join(clean['name'].split())
            if any(not re.fullmatch(r'#[0-9a-fA-F]{6}', clean[k]) for k in ('topColor', 'bottomColor', 'charColor')):
                raise ValueError('Invalid color')
            if not clean['name'] or len(clean['name']) > 100 or re.match(r'^(※|注[意：:]|対象年齢|発売元|販売元|©|Copyright)', clean['name'], re.I):
                clean['name'] = '種類未確認'
            if re.fullmatch(r'(タイプ|アイテム)\s*\d+', clean['name']):
                clean['name'] = '種類未確認'
            row['items'].append(clean)
        row['totalTypes'] = source.get('totalTypes')
        if row['totalTypes'] is not None and (not isinstance(row['totalTypes'], int) or not 1 <= row['totalTypes'] <= 1000):
            raise ValueError('Invalid type count')
        row['sourceUrl'] = source.get('sourceUrl') or (
            f"https://gacha-island.jp/{row['id'][3:]}/"
            if re.fullmatch(r'gi-\d+', row['id']) else None)
        row['retrievedAt'] = source.get('retrievedAt')
        rows.append(row)
    if not rows:
        raise ValueError('Empty catalog')
    series = [{k: s[k] for k in ('id', 'name', 'accentColor')} for s in raw['series']]
    series_ids = [s['id'] for s in series]
    if len(set(series_ids)) != len(series_ids) or any(r['seriesId'] not in series_ids for r in rows):
        raise ValueError('Invalid series')
    return {'format': 'facts-v1', 'version': raw.get('version', 1),
            'series': series, 'gachas': rows}


def publish(raw, target):
    data = facts(raw)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temporary.replace(target)
    return data


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('source')
    p.add_argument('target')
    args = p.parse_args()
    publish(json.loads(Path(args.source).read_text(encoding='utf-8')), args.target)
