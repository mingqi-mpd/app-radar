#!/usr/bin/env python3
"""US iPhone free category charts; standard-library-only daily snapshot collector."""
import datetime as dt
import json
from pathlib import Path
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CATEGORIES = {'Games':6014,'Finance':6015,'Shopping':6024,'Casino':7006,
              'Sports':6004,'Social Networking':6005,'Utilities':6002,'Entertainment':6016}
TZ = ZoneInfo('Europe/Rome')

def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def fetch(category, gid):
    url = f'https://itunes.apple.com/us/rss/topfreeapplications/limit=100/genre={gid}/json'
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                raw = json.load(response)
            feed = raw['feed']
            if feed['title']['label'] != f'iTunes Store: Top Free Applications in {category}':
                raise ValueError('Unexpected chart identity')
            stamp = dt.datetime.fromisoformat(feed['updated']['label'])
            age = dt.datetime.now(dt.timezone.utc) - stamp
            if not dt.timedelta(hours=-1) <= age <= dt.timedelta(hours=36):
                raise ValueError('Source timestamp is stale or in the future')
            entries = feed['entry']
            apps = []
            for rank, e in enumerate(entries, 1):
                app_id = e['id']['attributes']['im:id']
                if not app_id.isdigit() or float(e['im:price']['attributes']['amount']) != 0:
                    raise ValueError('Invalid app ID or non-free app')
                apps.append({'id':app_id, 'rank':rank, 'name':e['im:name']['label'],
                             'developer':e['im:artist']['label'],
                             'url':f'https://apps.apple.com/us/app/id{app_id}'})
            if len(apps) != 100 or len({a['id'] for a in apps}) != 100:
                raise ValueError('Expected exactly 100 unique apps')
            return {'category':category, 'source':url, 'source_updated':stamp.isoformat(),
                    'collected_at':dt.datetime.now(TZ).isoformat(), 'apps':apps}
        except Exception as exc:
            error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(str(error))

def lookup_ratings(app_ids, batch_size=100):
    """Return {app_id: US App Store rating count} via Apple's public lookup API.

    Missing IDs are omitted; a failed batch is skipped so ratings never block collection.
    """
    counts = {}
    ids = sorted(set(app_ids))
    for start in range(0, len(ids), batch_size):
        batch = ids[start:start + batch_size]
        url = f'https://itunes.apple.com/lookup?country=us&entity=software&id={",".join(batch)}'
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=25) as response:
                    raw = json.load(response)
                for item in raw.get('results', []):
                    app_id = str(item.get('trackId', ''))
                    if app_id in batch:
                        count = item.get('userRatingCount', 0)
                        counts[app_id] = int(count) if isinstance(count, (int, float)) else 0
                break
            except Exception:
                if attempt < 2:
                    time.sleep(attempt + 1)
    return counts


def main():
    from rolling import run
    return run()


if __name__ == '__main__':
    sys.exit(main())
