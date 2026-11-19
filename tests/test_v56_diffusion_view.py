"""v5.6 diffusion view: clean titles, similarity order, de-duplicated articles, outlet details."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_graph as G  # noqa: E402
import semantic  # noqa: E402
from test_v55_graph import ENTRIES, art  # noqa: E402

PROFILES = {'a.com': {'name': 'Alpha', 'lean': -1, 'kind': 'news', 'paywall': 'metered'},
            'b.com': {'name': 'Beta', 'lean': 1, 'kind': 'news'},
            'agg.example': {'name': 'agg.example', 'lean': None, 'kind': 'unclassified'}}
profile = lambda h: PROFILES.get(h, {'name': h, 'lean': 0, 'kind': 'news'})


class Titles(unittest.TestCase):
    def test_publisher_suffix_removed(self):
        self.assertEqual(G.clean_title('Nvidia stops shipping AI chips to China - Reuters'), 'Nvidia stops shipping AI chips to China')
        self.assertEqual(G.clean_title('Markets rally as inflation cools | Mint'), 'Markets rally as inflation cools')
        self.assertEqual(G.clean_title('Short - X'), 'Short - X')  # too short to be sure it is a suffix
        self.assertEqual(G.clean_title('  spaced   out title without any publisher  '), 'spaced out title without any publisher')


class View(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(semantic, 'ready', lambda: False)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def entries(self):
        extra = [art(11, 'agg.example', 's1', 'RBI holds repo rate steady as inflation cools - agg.example', '2099-01-02T00:00:00Z'),
                 art(12, 'agg.example', 's1', 'RBI holds repo rate steady as inflation cools - agg.example', '2099-01-03T00:00:00Z')]
        return ENTRIES + extra

    def test_related_sorted_by_similarity(self):
        d = G.diffuse(self.entries(), 'a1', None, profile, days=100000)
        sims = [c['similarity'] for c in d['related']]
        self.assertEqual(sims, sorted(sims, reverse=True))

    def test_title_prefers_rated_outlet_and_duplicates_collapse(self):
        d = G.diffuse(self.entries(), 'a1', None, profile, days=100000)
        st = d['seed_story']
        self.assertNotIn('agg.example', st['title'])          # the newest article is the aggregator's; not used as title
        self.assertEqual(sum(1 for i in st['articles'] if i in ('a11', 'a12')), 1)  # same outlet, same headline once
        self.assertTrue(st['first'])

    def test_outlet_details_returned(self):
        d = G.diffuse(self.entries(), 'a1', None, profile, days=100000, pref_of=lambda h: 'primary' if h == 'b.com' else '')
        o = d['outlets']
        self.assertEqual(o['a.com']['lean'], -1)
        self.assertEqual(o['a.com']['paywall'], 'metered')
        self.assertTrue(o['b.com']['primary'])
        self.assertFalse(o['agg.example']['known'])
        self.assertTrue(o['a.com']['known'])


if __name__ == '__main__':
    unittest.main()
