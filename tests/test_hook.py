"""A smaller working copy must not conceal staged growth."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATCHET = shutil.which('ratchet') or ROOT / '.cache/ratchet-env/bin/ratchet'


@unittest.skipUnless(Path(RATCHET).is_file(), 'Ratchet 0.2.3 required')
class GrowthHookTests(unittest.TestCase):
    def test_staged_growth_and_missing_prerequisites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                subprocess.run(['git', '-C', directory, *args], check=True,
                               capture_output=True)

            def check(expected, mode='check'):
                result = subprocess.run([str(ROOT / 'templates/pre-commit'), mode],
                                        cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

            git('init', '-q')
            git('config', 'user.name', 'Budget test')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            binary = root / '.cache/ratchet-env/bin/ratchet'
            binary.parent.mkdir(parents=True)
            binary.symlink_to(Path(RATCHET).resolve())
            (root / '.gitignore').write_text('.cache/\n')
            source = root / 'a.py'
            source.write_text('x = 1\n')
            (root / '.ratchet.json').write_text(json.dumps({
                'groups': {'source': {'include': ['*.py'], 'extensions': ['.py']}},
                'ceilings': {'source': 1}, 'max_file_lines': 2000, 'file_ceilings': {}}))
            git('add', '.gitignore', 'a.py', '.ratchet.json')
            check(0)
            git('commit', '-qm', 'baseline')
            source.write_text('x = 1\ny = 2\n')
            git('add', 'a.py')
            source.write_text('x = 1\n')
            check(1)
            policy = root / '.ratchet.json'
            config = json.loads(policy.read_text())
            config['ceilings']['source'] = 2
            policy.write_text(json.dumps(config))
            git('add', '.ratchet.json')
            check(1)  # An unstaged shrink cannot justify a staged ceiling raise.
            config['ceilings']['source'] = 1
            policy.write_text(json.dumps(config))
            subprocess.run([str(binary), '-C', directory, 'grant', '+1', '--reason',
                            'test feature', '--by', 'Budget test'], check=True, capture_output=True)
            git('add', '.ratchet.json', '.ratchet-grants.jsonl')
            check(0)
            git('commit', '-qm', 'granted growth')
            git('add', 'a.py')  # The smaller working file is now staged.
            (root / 'untracked.py').write_text('extra = 1\n' * 500)
            check(0, 'budget')
            check(0, 'tighten')
            self.assertEqual(json.loads(policy.read_text())['ceilings']['source'], 1)
            self.assertEqual((root / 'untracked.py').read_text().count('\n'), 500)
            check(2, 'tighten')  # Do not overwrite the newly unstaged policy.
            git('add', '.ratchet.json')
            check(0)
            source.write_text('x = 1\ny = 2\n')
            git('add', 'a.py')
            check(1)  # The 500 untracked lines supplied no room for regrowth.
            git('rm', '--cached', '.ratchet.json')
            check(2)
            binary.unlink()
            check(2)
