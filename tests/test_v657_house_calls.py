"""Wikipedia's winner tick and "Incumbent re-elected" both count as a call; uncalled seats are not counted as losses."""
import json
import unittest

import us_live as L
import wikitables as W

HEAD = ('<table class="wikitable"><tbody><tr><th colspan="2">District</th><th colspan="4">Incumbent</th><th rowspan="2">Candidates</th></tr>'
        '<tr><th>Location</th><th>2026 PVI</th><th>Member</th><th>Party</th><th>First elected</th><th>Status</th></tr>')
TICK = '<span typeof="mw:File"><img alt="Green tick" src="//upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Green_check.svg/13px-Green_check.svg.png" width="13"></span> '


def row(loc, party, status, cands):
    return f'<tr><td>{loc}</td><td>R+1</td><td>X</td><td>{party}</td><td>2020</td><td>{status}</td><td><ul>{cands}</ul></td></tr>'


PAGE = HEAD + ''.join([
    # Status still says the pre-election "renominated", but editors ticked the winner: decided.
    row('Ohio 9', 'Democratic', 'Incumbent renominated.', f'<li>{TICK}Ann Kirk (Democratic) 52.0%</li><li>Bo Lane (Republican) 48.0%</li>'),
    # Re-elected with no percentages and no tick: the incumbent's party won.
    row('Ohio 3', 'Democratic', 'Incumbent re-elected.', '<li>Cy Moss (Democratic)</li><li>Di Park (Republican)</li>'),
    # A tick but the status says too close to call: not called.
    row('Ohio 13', 'Democratic', 'Too close to call.', f'<li>{TICK}Ed Ray (Democratic) 50.1%</li><li>Fay Ho (Republican) 49.9%</li>'),
    # Nothing decided yet.
    row('Ohio 1', 'Republican', 'Incumbent running.', '<li>Gil Ma (Republican) 49%</li><li>Hal Ng (Democratic) 47%</li>'),
]) + '</tbody></table>'


class HouseCalls(unittest.TestCase):
    def test_tick_is_read_as_text(self):
        t = W.tables(PAGE)[0]
        self.assertTrue(t['rows'][0][-1]['lines'][0].startswith('✓'))

    def test_calls(self):
        rs = {r['id']: r for r in L.parse_page('H', 2026, PAGE)}
        self.assertEqual((rs['H-2026-OH-9']['called'], rs['H-2026-OH-9']['winner']), (1, 'Ann Kirk'))
        self.assertEqual((rs['H-2026-OH-3']['called'], rs['H-2026-OH-3']['winner'], rs['H-2026-OH-3']['winner_party']), (1, 'Cy Moss', 'D'))
        self.assertEqual(rs['H-2026-OH-13']['called'], 0)
        self.assertEqual(rs['H-2026-OH-1']['called'], 0)
        self.assertEqual(json.loads(rs['H-2026-OH-9']['cands'])[0][0], 'Ann Kirk')

    def test_big_images_are_not_ticks(self):
        self.assertFalse(W._is_check({'alt': 'Green tick', 'width': '120'}))
        self.assertTrue(W._is_check({'alt': '', 'src': '//x/13px-Green_check.svg.png', 'width': '13'}))


if __name__ == '__main__':
    unittest.main()


class EveryOfficeBuilds(unittest.TestCase):
    """Each office's summary builds without the downloaded results pack (guards against a name used before it is set)."""
    def test_all_offices(self):
        import sqlite3
        from unittest import mock
        import us_elections as UE

        def con():
            c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
            c.execute('CREATE TABLE races (office, cycle, state, seat)')
            return c
        base = {'cycle': 2024, 'special': 0, 'called': 1, 'winner': 'A', 'winner_party': 'D', 'runner': 'B', 'runner_party': 'R',
                'margin_pct': 4.0, 'unopposed': 0, 'cands': json.dumps([['A', 'D', 60, 60.0, 1], ['B', 'R', 40, 40.0, 0]])}
        with mock.patch.object(UE, '_con', con), mock.patch.object(UE, '_rows', lambda *a, **k: []), \
                mock.patch.object(UE.UD, 'electoral_votes', lambda ap, cy: {'OH': 17}), \
                mock.patch.object(UE.UD, 'apportionment', lambda rows: {}):
            h = UE.house(2024, [{**base, 'state': 'OH', 'seat': '1'}])
            self.assertEqual(h['popular_vote_races'], 1)
            self.assertIn('parties', UE.senate(2024, [{**base, 'state': 'OH', 'seat': 'I'}]))
            self.assertIn('parties', UE.governors(2024, [{**base, 'state': 'OH', 'seat': ''}]))
            p = UE.president(2024, [{**base, 'state': 'OH', 'seat': ''}])
            self.assertEqual(p['parties'][0]['seats'], 17)
