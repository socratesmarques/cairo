import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.config import Settings
from cairo.integrations import desktop_music
from cairo.integrations.window_layout import half_rect
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.desktop_commands import parse_desktop_commands


class CompoundDesktopTests(unittest.TestCase):
    def test_exact_spoken_examples_and_native_target(self):
        for phrase in ('abra youtube music desktop e toque a musica Nuts', 'Abra o YouTube Music Desktop App e reproduza a música "Nuts".', 'Toque Nuts no YouTube Music Desktop'):
            self.assertEqual(parse_desktop_commands(phrase), [("desktop_play_music", {"query": "Nuts"})])
        self.assertEqual(parse_desktop_commands('Abra o visual Studio code e colocar na direita'), [
            ("open_app", {"app": "vscode"}), ("window_action", {"app": "vscode", "action": "snap_right"})])
        self.assertEqual(parse_desktop_commands('Abra VS Code e coloque na esquerda')[-1][1]["action"], "snap_left")
        for phrase in ('Não toque Nuts no YouTube Music Desktop', 'Explique como abra o visual Studio code e colocar na direita'):
            self.assertIsNone(parse_desktop_commands(phrase))

    def test_half_monitor_handles_negative_origins_odd_widths_and_taskbar(self):
        self.assertEqual(half_rect((0, 0, 1920, 1040), "right"), (960, 0, 960, 1040))
        self.assertEqual(half_rect((-1919, 40, 0, 1080), "left"), (-1919, 40, 959, 1040))
        self.assertEqual(half_rect((-1919, 40, 0, 1080), "right"), (-960, 40, 960, 1040))
        with self.assertRaises(ValueError):
            half_rect((1, 1, 0, 0), "right")

    def test_search_track_reads_metadata_without_executing_html(self):
        data = {"contents": [{"videoRenderer": {"videoId": "abcdefghijk", "title": {"runs": [{"text": "Other song"}]}}},
                             {"videoRenderer": {"videoId": "lmnopqrstuv", "title": {"simpleText": "Nuts"}}}]}
        html = ('<script>var ytInitialData = ' + json.dumps(data) + '; alert("not executed")</script>').encode()
        response = io.BytesIO(html)
        with patch('cairo.models.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            track = desktop_music.search_track("Nuts")
        self.assertEqual(track, {"id": "lmnopqrstuv", "title": "Nuts"})

    def test_desktop_music_uses_registered_uri_and_never_claims_verified_playback(self):
        with patch('winreg.OpenKey'), patch.object(desktop_music, 'search_track', return_value={"id": "abcdefghijk", "title": "Nuts"}), patch.object(desktop_music.os, 'startfile') as launch:
            result = desktop_music.play_music('Nuts')
        launch.assert_called_once_with('ytmd://play/abcdefghijk', 'open')
        self.assertTrue(result['requested'])
        self.assertIsNone(result['playing'])
        with patch('winreg.OpenKey', side_effect=FileNotFoundError), patch.object(desktop_music.os, 'startfile') as launch:
            with self.assertRaises(FileNotFoundError):
                desktop_music.play_music('Nuts')
            launch.assert_not_called()

    def test_open_then_snap_runs_in_order_without_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = Orchestrator(Settings(workspace=root/'work', data_dir=root/'data', allow_desktop=True))
            calls = []
            try:
                sid = app.memory.create_session()['id']
                with patch.object(app.tools.desktop, 'open_app', side_effect=lambda **kw: calls.append(('open', kw)) or {"message": "Aberto"}), patch.object(app.tools.desktop, 'window_action', side_effect=lambda **kw: calls.append(('snap', kw)) or {"message": "À direita"}), patch.object(app.model, 'complete', side_effect=AssertionError('No model needed')):
                    run = app.submit(sid, 'Abra o visual Studio code e colocar na direita', 'normal')
                    for _ in range(100):
                        result = app.memory.run(run['id'])
                        if result['status'] in {'completed','failed'}:
                            break
                        time.sleep(0.02)
                self.assertEqual(result['status'], 'completed', result)
                self.assertEqual(calls, [('open', {'app':'vscode'}), ('snap', {'app':'vscode', 'action':'snap_right'})])
                denied = json.loads(app.tools.execute('desktop_play_music', {'query':'Nuts'}, 'SystemAgent', sid, allow_ui_actions=False))
                self.assertFalse(denied['ok'])
            finally:
                app.close()
