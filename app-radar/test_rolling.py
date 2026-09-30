import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest

from rolling import fresh, advance, run, add_ratings, CATEGORIES, WINDOW_DAYS


def charts(**overrides):
    return {
        category: {
            'apps': [
                {'id': app_id, 'name': app_id, 'developer': 'Test', 'rank': rank + 1}
                for rank, app_id in enumerate(overrides.get(category, ['known']))
            ]
        }
        for category in CATEGORIES
    }


class RollingTests(unittest.TestCase):
    def test_today_is_baseline_and_tomorrow_compares_with_today(self):
        day = dt.date(2026, 9, 28)
        state = advance(fresh(day), day, charts(Games=['A']), {})
        self.assertTrue(state['latest']['is_baseline'])
        self.assertEqual(state['latest']['leads'], [])
        state = advance(
            state,
            day + dt.timedelta(days=1),
            charts(Games=['B'], Casino=['A', 'B']),
            {},
        )
        self.assertEqual([lead['id'] for lead in state['latest']['leads']], ['B'])
        self.assertEqual(len(state['latest']['leads'][0]['charts']), 2)
        self.assertEqual(state['latest']['unrecorded_history_days'], 29)

    def test_app_qualifies_again_after_thirty_absent_days(self):
        day = dt.date(2026, 1, 1)
        state = advance(fresh(day), day, charts(Games=['A']), {})
        for offset in range(1, 30):
            state = advance(state, day + dt.timedelta(days=offset), charts(), {})
        # Day 30: day 0 is still inside the previous-30-day window.
        at_thirty = advance(copy.deepcopy(state), day + dt.timedelta(days=30), charts(Games=['A']), {})
        self.assertEqual(at_thirty['latest']['leads'], [])
        state = advance(state, day + dt.timedelta(days=30), charts(), {})
        state = advance(state, day + dt.timedelta(days=31), charts(Games=['A']), {})
        self.assertEqual([lead['id'] for lead in state['latest']['leads']], ['A'])

    def test_only_thirty_calendar_days_are_retained(self):
        day = dt.date(2026, 1, 1)
        state = fresh(day)
        for offset in range(45):
            state = advance(state, day + dt.timedelta(days=offset), charts(), {})
        self.assertEqual(len(state['days']), WINDOW_DAYS)
        self.assertEqual(min(state['days']), '2026-01-16')
        self.assertEqual(max(state['days']), '2026-02-14')

    def test_long_gap_does_not_create_a_second_baseline(self):
        day = dt.date(2026, 1, 1)
        state = advance(fresh(day), day, charts(Games=['A']), {})
        state = advance(state, day + dt.timedelta(days=40), charts(Games=['B']), {})
        self.assertFalse(state['latest']['is_baseline'])
        self.assertEqual([lead['id'] for lead in state['latest']['leads']], ['B', 'known'])

    def test_partial_day_publishes_no_leads_but_suppresses_repeat(self):
        day = dt.date(2026, 9, 28)
        state = advance(fresh(day), day, charts(), {})
        tomorrow = day + dt.timedelta(days=1)
        state = advance(
            state,
            tomorrow,
            {'Games': charts(Games=['B'])['Games']},
            {'Finance': 'offline'},
        )
        self.assertFalse(state['latest']['complete'])
        self.assertEqual(state['latest']['leads'], [])
        state = advance(state, tomorrow + dt.timedelta(days=1), charts(Games=['B']), {})
        self.assertEqual(state['latest']['leads'], [])
        self.assertEqual(state['latest']['incomplete_history_dates'], [str(tomorrow)])

    def test_partial_same_day_rerun_keeps_earlier_ids(self):
        day = dt.date(2026, 9, 28)
        state = advance(fresh(day), day, charts(), {})
        tomorrow = day + dt.timedelta(days=1)
        state = advance(state, tomorrow, {'Games': charts(Games=['X'])['Games']}, {'Finance': 'offline'})
        state = advance(state, tomorrow, {'Finance': charts(Finance=['Y'])['Finance']}, {'Games': 'offline'})
        self.assertEqual(state['days'][str(tomorrow)]['ids'], ['X', 'Y'])
        self.assertFalse(state['days'][str(tomorrow)]['complete'])

    def test_annual_state_migrates_only_current_first_seen_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = dt.date(2026, 9, 28)
            (root / 'annual-state.json').write_text(json.dumps({
                'started_on': str(day),
                'seen': {'A': str(day)},
                'days': {str(day): True},
            }))
            def fetcher(category, genre):
                return charts(Games=['A'])[category]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run(root, day, fetcher), 0)
            state = json.loads((root / 'rolling-state.json').read_text())
            self.assertIn('A', state['days'][str(day)]['ids'])
            self.assertFalse((root / 'annual-state.json').exists())

    def test_rating_counts_are_attached_to_leads(self):
        day = dt.date(2026, 9, 28)
        state = advance(fresh(day), day, charts(), {})
        state = advance(state, day + dt.timedelta(days=1), charts(Games=['B', 'C']), {})
        add_ratings(state['latest'], lambda ids: {'B': 1234})
        counts = {lead['id']: lead['rating_count'] for lead in state['latest']['leads']}
        self.assertEqual(counts, {'B': 1234, 'C': None})

    def test_rating_lookup_failure_does_not_break_collection(self):
        def broken(ids):
            raise RuntimeError('offline')
        with tempfile.TemporaryDirectory() as tmp:
            root, day = Path(tmp), dt.date(2026, 9, 28)
            with contextlib.redirect_stdout(io.StringIO()):
                run(root, day, lambda c, g: charts()[c], broken)
                rc = run(root, day + dt.timedelta(days=1), lambda c, g: charts(Games=['B'])[c], broken)
            self.assertEqual(rc, 0)
            latest = json.loads((root / 'latest.json').read_text())
            self.assertIsNone(latest['leads'][0]['rating_count'])

    def test_same_day_rerun_backfills_missing_ratings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, day = Path(tmp), dt.date(2026, 9, 28)
            with contextlib.redirect_stdout(io.StringIO()):
                run(root, day, lambda c, g: charts()[c], lambda ids: {})
                tomorrow = day + dt.timedelta(days=1)
                run(root, tomorrow, lambda c, g: charts(Games=['B'])[c], lambda ids: {})
                def no_fetch(c, g):
                    raise AssertionError('charts must not be refetched')
                run(root, tomorrow, no_fetch, lambda ids: {'B': 42})
            latest = json.loads((root / 'latest.json').read_text())
            state = json.loads((root / 'rolling-state.json').read_text())
            self.assertEqual(latest['leads'][0]['rating_count'], 42)
            self.assertEqual(state['latest']['leads'][0]['rating_count'], 42)
            self.assertEqual(state['days'][str(tomorrow)]['ids'], ['B', 'known'])


class FeedTests(unittest.TestCase):
    NOW = dt.datetime(2026, 9, 30, 8, tzinfo=dt.timezone.utc)

    def feed(self, ids):
        return {'feed': {
            'title': {'label': 'iTunes Store: Top Free Applications in Finance'},
            'updated': {'label': '2026-09-30T00:25:51-07:00'},
            'entry': [{'id': {'attributes': {'im:id': i}}, 'im:price': {'attributes': {'amount': '0.00'}},
                       'im:name': {'label': i}, 'im:artist': {'label': 'Dev'}} for i in ids],
        }}

    def test_ninety_nine_entries_are_accepted(self):
        from radar import parse_feed
        _, apps = parse_feed(self.feed([str(i) for i in range(1, 100)]), 'Finance', self.NOW)
        self.assertEqual(len(apps), 99)

    def test_duplicates_keep_first_rank(self):
        from radar import parse_feed
        ids = [str(i) for i in range(1, 100)] + ['5']
        _, apps = parse_feed(self.feed(ids), 'Finance', self.NOW)
        self.assertEqual(len(apps), 99)
        self.assertEqual([a['rank'] for a in apps], list(range(1, 100)))

    def test_short_feed_is_rejected(self):
        from radar import parse_feed
        with self.assertRaises(ValueError):
            parse_feed(self.feed([str(i) for i in range(1, 60)]), 'Finance', self.NOW)


if __name__ == '__main__':
    unittest.main()
