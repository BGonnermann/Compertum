"""A manual shortcut reuses the right Hub and never takes another program's port."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    import launch
except ImportError: launch=None


class LauncherTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(launch,'The reusable manual launcher must exist')

    def test_existing_matching_hub_is_reused(self):
        with patch.object(launch,'probe',return_value='matching'),patch('webbrowser.open') as browser,patch.object(launch,'serve') as server:
            self.assertEqual(launch.start(),0);server.assert_not_called();browser.assert_called_once()

    def test_another_program_is_not_reused_or_stopped(self):
        with patch.object(launch,'probe',return_value='other'),patch('webbrowser.open') as browser,patch.object(launch,'serve') as server:
            self.assertEqual(launch.start(),1);browser.assert_not_called();server.assert_not_called()

    def test_missing_hub_starts_only_the_local_reader(self):
        with patch.object(launch,'probe',return_value='absent'),patch.object(launch,'serve',return_value=0) as server:
            self.assertEqual(launch.start(),0);server.assert_called_once_with(8767,True)

if __name__=='__main__': unittest.main()
