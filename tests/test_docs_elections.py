"""docs/ELECTIONS.md describes the models with numbers; this keeps the guide in step with the code."""
import unittest
from pathlib import Path

import forecast as F
import pulse as P

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / 'docs' / 'ELECTIONS.md').read_text(encoding='utf-8')


class GuideMatchesCode(unittest.TestCase):
    def test_forecast_settings(self):
        self.assertIn(f"{F.BAG['trees']} trees, depth {F.BAG['depth']}", DOC)
        self.assertIn(f"{F.BOOST['rounds']} shallow trees (depth {F.BOOST['depth']}", DOC)
        self.assertIn(f"learning rate {F.BOOST['lr']}", DOC)
        self.assertIn(f"{F.SIMS:,} simulated elections", DOC)
        self.assertIn(f'{len(F.FEATURES)} features', DOC)
        for f in F.FEATURES:
            self.assertIn(f'`{f}`', DOC, f)
        self.assertIn(f'**{"five" if F.TERM_YEARS == 5 else F.TERM_YEARS} years after the last one**', DOC)
        self.assertEqual(F.trust_label(0.8, 0.7), 'High'); self.assertEqual(F.trust_label(0.64, 0.9), 'Low')
        self.assertIn('≥80% calls with ≥70% coverage', DOC)

    def test_pulse_settings(self):
        self.assertIn(f'within the last {P.MOOD_WINDOW} months', DOC)
        self.assertIn(f'half-life is {P.MOOD_HALFLIFE} months', DOC)
        self.assertIn(f'{P.SIMS:,} simulations', DOC)
        self.assertIn(f'at least {P.SENT_MIN_ARTICLES} recent articles', DOC)
        self.assertIn(f'{P.SENT_GAIN} × (tone change', DOC)
        self.assertIn(f'{P.DRIFT_PER_YEAR * 100:g} vote-share points per year', DOC)
        self.assertEqual(set(P.HYPOTHESES), {'H1', 'H2', 'H3', 'H4', 'H5'})
        for h, (name, _) in P.HYPOTHESES.items():
            self.assertIn(f'**{h}**', DOC)

    def test_readme_links_the_guide(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('docs/ELECTIONS.md', readme)


if __name__ == '__main__':
    unittest.main()
