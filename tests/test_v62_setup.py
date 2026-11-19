"""v6.2: Windows one-click setup (Choice B) and the shared launchers.

These checks run on any OS. They do not execute the Windows scripts; they pin the
properties that break silently on Windows: line endings, ASCII-only PowerShell for
Windows PowerShell 5.1, the Python minimum, and the hand-off between the setup and
start_windows.bat.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / 'tools' / 'windows' / 'install_sanjaya.ps1'
SETUP_BAT = ROOT / 'install_sanjaya_windows.bat'
START_BAT = ROOT / 'start_windows.bat'
LM_BAT = ROOT / 'install_language_model.bat'


class WindowsScripts(unittest.TestCase):
    def test_files_exist(self):
        for p in (PS1, SETUP_BAT, START_BAT, LM_BAT):
            self.assertTrue(p.exists(), p)

    def test_ascii_only(self):
        # Windows PowerShell 5.1 reads a BOM-less .ps1 as the ANSI code page; cmd.exe the OEM one.
        for p in (PS1, SETUP_BAT, START_BAT, LM_BAT):
            p.read_bytes().decode('ascii')

    def test_gitattributes_keep_crlf(self):
        attrs = (ROOT / '.gitattributes').read_text(encoding='utf-8')
        self.assertIn('*.bat text eol=crlf', attrs)
        self.assertIn('*.ps1 text eol=crlf', attrs)

    def test_setup_bat_runs_the_script_and_then_starts(self):
        text = SETUP_BAT.read_text(encoding='utf-8')
        self.assertIn(r'tools\windows\install_sanjaya.ps1', text)
        self.assertIn('-ExecutionPolicy Bypass', text)
        self.assertIn('%*', text)                      # -Yes / -NoOllama / -NoShortcut pass through
        self.assertIn('start_windows.bat', text)

    def test_python_minimum_is_39_everywhere(self):
        ps = PS1.read_text(encoding='utf-8')
        self.assertIn("[version]'3.9'", ps)
        self.assertIn("$PY_VERSION = '3.12.10'", ps)
        self.assertIn('(3, 9)', START_BAT.read_text(encoding='utf-8'))
        self.assertNotIn('Python 3.10 or newer is required', START_BAT.read_text(encoding='utf-8'))

    def test_start_uses_the_python_the_setup_chose(self):
        ps, bat = PS1.read_text(encoding='utf-8'), START_BAT.read_text(encoding='utf-8')
        self.assertIn('.sanjaya_python.txt', ps)
        self.assertIn('.sanjaya_python.txt', bat)
        self.assertIn(r'.venv\Scripts\python.exe', bat)
        self.assertIn('"%PY%" server.py', bat)          # quoted: folders with spaces

    def test_downloads_are_signature_checked(self):
        ps = PS1.read_text(encoding='utf-8')
        self.assertIn("Signed-By $tmp 'Python Software Foundation'", ps)
        self.assertIn("Signed-By $tmp 'Ollama'", ps)

    def test_ollama_question_defaults_to_yes(self):
        self.assertRegex(PS1.read_text(encoding='utf-8'), r"Ask 'Install Ollama now\?' \$true")

    def test_ollama_model_matches_the_app_default(self):
        default = re.search(r"DEFAULT_MODEL = '([^']+)'", (ROOT / 'lm_labels.py').read_text(encoding='utf-8')).group(1)
        self.assertIn(f"$OLLAMA_MODEL = '{default}'", PS1.read_text(encoding='utf-8'))

    def test_lm_model_matches_semantic(self):
        model = re.search(r"MODEL = '([^']+)'", (ROOT / 'semantic.py').read_text(encoding='utf-8')).group(1)
        self.assertIn(model, PS1.read_text(encoding='utf-8'))

    def test_shortcut_uses_the_emblem(self):
        self.assertIn(r"static\favicon.ico", PS1.read_text(encoding='utf-8'))
        self.assertTrue((ROOT / 'static' / 'favicon.ico').exists())

    def test_no_powershell7_only_syntax(self):
        code = '\n'.join(l for l in PS1.read_text(encoding='utf-8').splitlines() if not l.lstrip().startswith('#'))
        for token in (' ?? ', ' ?. ', '&&', '||', '-Parallel'):
            self.assertNotIn(token, code)

    def test_local_files_are_ignored(self):
        ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
        for name in ('.venv/', '.sanjaya_python.txt', 'setup_log.txt', 'model_cache/'):
            self.assertIn(name, ignore)


class Readme(unittest.TestCase):
    def test_choices_are_documented(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('### 3.3 Choice A: build from the core', text)
        self.assertIn('### 3.4 Choice B: one-click setup (Windows)', text)
        self.assertIn('### 3.5 If part of the setup fails', text)
        self.assertIn('install_sanjaya_windows.bat', text)

    def test_launch_poster_is_in_the_repo(self):
        self.assertTrue((ROOT / 'docs' / 'brand' / 'sanjaya-launch-poster.png').exists())


if __name__ == '__main__':
    unittest.main()
