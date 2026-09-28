"""Rolling 30-day, cross-category App Store chart tracking."""
import concurrent.futures
import datetime as dt
import fcntl
import json
from pathlib import Path
import shutil

from radar import ROOT, CATEGORIES, TZ, fetch, atomic_json

WINDOW_DAYS = 30


def fresh(day):
    return {
        'schema': 2,
        'window_days': WINDOW_DAYS,
        'started_on': str(day),
        'baseline_date': None,
        'days': {},
        'latest': None,
    }


def migrate_annual(root, day):
    """Use only first-seen IDs from the current baseline; never import old snapshots."""
    old_path = root / 'annual-state.json'
    if not old_path.exists():
        return fresh(day), False
    old = json.loads(old_path.read_text())
    state = fresh(day)
    state['started_on'] = old.get('started_on', str(day))
    state['baseline_date'] = old.get('baseline_date')
    grouped = {}
    for app_id, first_seen in old.get('seen', {}).items():
        grouped.setdefault(first_seen, set()).add(app_id)
    for date, ids in grouped.items():
        try:
            parsed = dt.date.fromisoformat(date)
        except ValueError:
            continue
        if parsed <= day:
            state['days'][date] = {
                'complete': bool(old.get('days', {}).get(date, False)),
                'ids': sorted(ids),
            }
    return state, True


def cleanup_old_data(root, day):
    """Keep only exact dated folders inside the 30-day retained range."""
    data = root / 'data'
    cutoff = day - dt.timedelta(days=WINDOW_DAYS - 1)
    if not data.exists():
        return
    for folder in data.iterdir():
        if folder.is_symlink() or not folder.is_dir():
            continue
        try:
            parsed = dt.date.fromisoformat(folder.name)
        except ValueError:
            continue
        if folder.name == str(parsed) and parsed < cutoff:
            shutil.rmtree(folder)


def advance(state, day, snapshots, errors):
    date = str(day)
    old = state.get('latest')
    if 'baseline_date' not in state:
        state['baseline_date'] = (
            old['date'] if old and old.get('complete') and old.get('is_baseline') else None
        )
    if old and old['date'] > date:
        raise ValueError('Clock moved backwards; refusing to overwrite newer data')
    if old and old['date'] == date and old['complete']:
        return state

    comparison_start = day - dt.timedelta(days=WINDOW_DAYS)
    comparison_end = day - dt.timedelta(days=1)
    prior_days = {}
    for stored_date, record in state['days'].items():
        parsed = dt.date.fromisoformat(stored_date)
        if comparison_start <= parsed <= comparison_end:
            prior_days[stored_date] = record
    prior_seen = {app_id for record in prior_days.values() for app_id in record['ids']}

    current_ids = {
        app['id']
        for snapshot in snapshots.values()
        for app in snapshot['apps']
    }
    complete = len(snapshots) == len(CATEGORIES) and not errors
    is_baseline = complete and not state['baseline_date']
    if is_baseline:
        state['baseline_date'] = date
    leads = {}
    if complete and not is_baseline:
        for category, snapshot in snapshots.items():
            for app in snapshot['apps']:
                if app['id'] not in prior_seen:
                    lead = leads.setdefault(
                        app['id'], {**app, 'first_seen': date, 'charts': []}
                    )
                    lead['charts'].append({'category': category, 'rank': app['rank']})

    same_day = state['days'].get(date)
    if same_day and not complete:
        # A partial rerun must not discard IDs observed by an earlier partial run today.
        current_ids |= set(same_day['ids'])
    state['days'][date] = {'complete': complete, 'ids': sorted(current_ids)}
    retained_from = day - dt.timedelta(days=WINDOW_DAYS - 1)
    state['days'] = {
        stored_date: record
        for stored_date, record in state['days'].items()
        if retained_from <= dt.date.fromisoformat(stored_date) <= day
    }
    incomplete = sorted(
        stored_date for stored_date, record in prior_days.items() if not record['complete']
    )
    state['latest'] = {
        'date': date,
        'timezone': 'Europe/Rome',
        'country': 'US',
        'device': 'iPhone',
        'chart': 'Top Free',
        'rule': 'rolling-30-day-absence',
        'window_days': WINDOW_DAYS,
        'started_on': state['started_on'],
        'baseline_date': state['baseline_date'],
        'comparison_from': str(comparison_start),
        'comparison_to': str(comparison_end),
        'retained_from': str(retained_from),
        'history_days': len(prior_days),
        'complete_history_days': sum(1 for record in prior_days.values() if record['complete']),
        'incomplete_history_dates': incomplete,
        'unrecorded_history_days': WINDOW_DAYS - len(prior_days),
        'complete': complete,
        'is_baseline': is_baseline,
        'observed_count': len(current_ids),
        'leads': list(leads.values()),
        'errors': errors,
        'coverage': {
            category: {
                'ready': complete and not is_baseline,
                'current_available': category in snapshots,
            }
            for category in CATEGORIES
        },
    }
    return state


def run(root=ROOT, today=None, fetcher=fetch):
    root = Path(root)
    day = today or dt.datetime.now(TZ).date()
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.rolling.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = root / 'rolling-state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            migrated = False
        else:
            state, migrated = migrate_annual(root, day)
        latest = state.get('latest')
        if 'baseline_date' not in state:
            state['baseline_date'] = (
                latest['date']
                if latest and latest.get('complete') and latest.get('is_baseline')
                else None
            )
            if latest:
                latest['baseline_date'] = state['baseline_date']
            atomic_json(state_path, state)
        if latest and latest['date'] == str(day) and latest['complete']:
            atomic_json(root / 'latest.json', latest)
            print(json.dumps({'date': str(day), 'status': 'already_collected'}))
            return 0

        snapshots, errors = {}, {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(fetcher, category, genre): category
                    for category, genre in CATEGORIES.items()}
            for future in concurrent.futures.as_completed(jobs):
                category = jobs[future]
                try:
                    snapshots[category] = future.result()
                except Exception as exc:
                    errors[category] = str(exc)
        if today is None and dt.datetime.now(TZ).date() != day:
            raise ValueError('Date changed during collection; rerun')

        state = advance(state, day, snapshots, errors)
        cleanup_old_data(root, day)
        atomic_json(state_path, state)
        if migrated:
            (root / 'annual-state.json').unlink(missing_ok=True)
        report = state['latest']
        atomic_json(root / 'latest.json', report)
        (root / '今日榜单.md').write_text(
            f'# App Radar · {day}\n\nRolling {WINDOW_DAYS}-day absence across all eight categories.\n\n'
            f'Complete: {report["complete"]}. History days: {report["history_days"]}. '
            f'New apps: {len(report["leads"])}.\n',
            encoding='utf-8',
        )
        print(json.dumps({
            'date': str(day),
            'complete': report['complete'],
            'history_days': report['history_days'],
            'observed_count': report['observed_count'],
            'new_apps': len(report['leads']),
            'errors': errors,
        }, ensure_ascii=False))
        return 0 if report['complete'] else 1
