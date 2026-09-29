"""Export rolling 30-day results without private history or diagnostic errors."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
source=root.parent/'app-radar'
report=json.loads((source/'latest.json').read_text())
assert report['rule'] == 'rolling-30-day-absence'
keys = ('date', 'timezone', 'country', 'device', 'chart', 'rule', 'window_days',
        'started_on', 'comparison_from', 'comparison_to', 'retained_from',
        'history_days', 'complete_history_days', 'incomplete_history_dates',
        'unrecorded_history_days', 'complete', 'is_baseline', 'observed_count',
        'coverage', 'leads')
public = {key: report[key] for key in keys}
public['ratings_checked_at'] = report.get('ratings_checked_at')
if not report['complete'] or report['is_baseline']:
    assert not public['leads']
temp = root / 'dist/data.tmp'
temp.write_text(json.dumps(public, ensure_ascii=False), encoding='utf-8')
temp.replace(root / 'dist/data.json')
print(f'Exported {len(public["leads"])} rolling-window apps; complete={public["complete"]}')
