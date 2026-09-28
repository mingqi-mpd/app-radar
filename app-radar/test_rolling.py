import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest

from rolling import fresh, advance, run, CATEGORIES, WINDOW_DAYS


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


if __name__ == '__main__':
    unittest.main()
