"""Export rolling 30-day results without private history or diagnostic errors."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
source = root.parent / 'app-radar'
MAX_DAYS = 7

report = json.loads((source / 'latest.json').read_text())
assert report['rule'] == 'rolling-30-day-absence'
keys = ('date', 'timezone', 'country', 'device', 'chart', 'rule', 'window_days',
        'started_on', 'comparison_from', 'comparison_to', 'retained_from',
        'history_days', 'complete_history_days', 'incomplete_history_dates',
        'unrecorded_history_days', 'complete', 'is_baseline', 'observed_count',
        'coverage', 'leads')
day_keys = ('date', 'complete', 'is_baseline', 'history_days', 'coverage', 'leads')


def check(r):
    if not r['complete'] or r['is_baseline']:
        assert not r['leads']


public = {key: report[key] for key in keys}
public['ratings_checked_at'] = report.get('ratings_checked_at')
check(public)

days = {}
for path in sorted((source / 'history').glob('*.json'), reverse=True):
    past = json.loads(path.read_text())
    if past.get('rule') == 'rolling-30-day-absence' and past['date'] <= report['date']:
        days[past['date']] = {key: past[key] for key in day_keys}
days[report['date']] = {key: report[key] for key in day_keys}
public['recent_days'] = [days[d] for d in sorted(days, reverse=True)[:MAX_DAYS]]
for day in public['recent_days']:
    check(day)

temp = root / 'dist/data.tmp'
temp.write_text(json.dumps(public, ensure_ascii=False), encoding='utf-8')
temp.replace(root / 'dist/data.json')
print(f'Exported {len(public["leads"])} rolling-window apps; complete={public["complete"]}; '
      f'days={len(public["recent_days"])}')
