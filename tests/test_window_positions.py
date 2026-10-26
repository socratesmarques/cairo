import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.config import Settings
from cairo.integrations.app_discovery import record, window_identity
from cairo.integrations.desktop_control import DesktopController
from cairo.integrations.window_geometry import POSITIONS, placement
from cairo.integrations.window_layout import act_on_target
from cairo.integrations.window_native import WindowTarget
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.desktop_commands import parse_desktop_commands
from cairo.orchestrator.window_commands import parse_window_command


class FakeWindows:
    def __init__(self, minimum=(1, 1), refuse=False):
        self.rect = (100, 100, 1100, 900)
        self.minimum = minimum
        self.refuse = refuse
        self.moves = []
        self.closed = False

    def find(self, target): return 123
    def pid(self, hwnd): return 77
    def maximized(self, hwnd): return False
    def bounds(self, hwnd): return self.rect
    def show(self, hwnd, state): pass
    def monitor_for(self, hwnd): return 10
    def focus(self, hwnd): return True
    def close(self): self.closed = True
    def monitors(self):
        return [
            {"id": 1, "handle": 10, "primary": True, "work": [0, 0, 1920, 1040]},
            {"id": 2, "handle": 20, "primary": False, "work": [-1280, 0, 0, 984]},
        ]
    def move(self, hwnd, rect):
        self.moves.append(rect)
        if not self.refuse:
            x, y, w, h = rect
            self.rect = (x, y, x + max(w, self.minimum[0]), y + max(h, self.minimum[1]))


class WindowPositionTests(unittest.TestCase):
    def test_dynamic_apps_all_edges_corners_and_center(self):
        for phrase, action in [
            ("esquerda", "snap_left"), ("direita", "snap_right"),
            ("cima", "snap_top"), ("baixo", "snap_bottom"),
            ("canto superior esquerdo", "snap_top_left"), ("canto superior direito", "snap_top_right"),
            ("canto inferior esquerdo", "snap_bottom_left"), ("canto inferior direito", "snap_bottom_right"),
            ("centro", "center"),
        ]:
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_desktop_commands("Abra Meu Aplicativo e coloque na " + phrase, discover_apps=True), [
                    ("open_app", {"app": "Meu Aplicativo"}), ("window_action", {"app": "Meu Aplicativo", "action": action})])
                self.assertEqual(parse_desktop_commands("Mova Meu Aplicativo pra " + phrase, discover_apps=True), [
                    ("window_action", {"app": "Meu Aplicativo", "action": action})])

    def test_window_ids_monitors_coordinates_and_negations(self):
        self.assertEqual(parse_desktop_commands("Mova Firefox para o canto superior direito no monitor 2", discover_apps=True),
            [("window_action", {"app": "Firefox", "action": "snap_top_right", "monitor": 2})])
        self.assertEqual(parse_desktop_commands("Posicione Chrome em x 100 y 80 com largura 900 e altura 600")[-1][1],
            {"app": "chrome", "action": "custom", "x": 100, "y": 80, "width": 900, "height": 600})
        self.assertEqual(parse_desktop_commands("Mova a janela win:123:77 para cima"),
            [("window_action", {"app": "win:123:77", "action": "snap_top"})])
        percent = parse_desktop_commands("Posicione Chrome em x 25% y 10% com largura 50% e altura 60%")[-1][1]
        self.assertEqual(percent["unit"], "percent")
        for phrase in ("Não mova Firefox para cima", "Explique como mover Firefox para cima", "Mova Chrome; execute comando para cima"):
            self.assertIsNone(parse_window_command(phrase, discover_apps=True))
        self.assertIsNone(parse_window_command("Abra Desconhecido na direita", discover_apps=False))

    def test_geometry_tiles_odd_negative_monitors_without_gaps(self):
        work = (-1919, 40, 0, 1080)
        left = placement(work, "left", work)
        right = placement(work, "right", work)
        top = placement(work, "top", work)
        bottom = placement(work, "bottom", work)
        self.assertEqual(left[2]+right[2], 1919)
        self.assertEqual(top[3]+bottom[3], 1040)
        self.assertEqual(left[0]+left[2], right[0])
        self.assertEqual(top[1]+top[3], bottom[1])
        for position in POSITIONS.keys() - {"custom"}:
            x, y, w, h = placement(work, position, (-1800, 100, -1000, 700))
            self.assertTrue(work[0] <= x < x+w <= work[2])
            self.assertTrue(work[1] <= y < y+h <= work[3])
        self.assertEqual(placement((0, 0, 1920, 1040), "custom", work, x=25, y=10, width=50, height=60, unit="percent"), (480, 104, 960, 624))
        with self.assertRaises(ValueError):
            placement((0, 0, 1920, 1040), "custom", work, x=1900, y=100, width=900, height=600)

    def test_verified_placement_on_selected_monitor(self):
        native = FakeWindows()
        with patch('cairo.integrations.window_layout.Windows', return_value=native):
            result = act_on_target(WindowTarget('Example', app_id='example!App'), 'snap_top_right', monitor=2)
        self.assertTrue(result['positioned'])
        self.assertTrue(result['exact'])
        self.assertEqual(result['monitor'], 2)
        self.assertEqual(result['bounds'], [-640, 0, 0, 492])
        self.assertTrue(native.closed)

    def test_minimum_size_adjustment_is_reported_and_stays_on_screen(self):
        native = FakeWindows(minimum=(800, 600))
        with patch('cairo.integrations.window_layout.Windows', return_value=native), patch('cairo.integrations.window_layout.POSITION_SETTLE_SECONDS', 0):
            result = act_on_target(WindowTarget('Minimum-size app', executable='example.exe'), 'snap_bottom_right')
        self.assertFalse(result['exact'])
        self.assertTrue(result['adjusted'])
        self.assertEqual(result['bounds'], [960, 440, 1920, 1040])
        self.assertIn('restrições', result['message'])

    def test_refusal_and_invalid_monitor_never_report_success(self):
        native = FakeWindows(refuse=True)
        with patch('cairo.integrations.window_layout.Windows', return_value=native), patch('cairo.integrations.window_layout.POSITION_SETTLE_SECONDS', 0):
            with self.assertRaises(ValueError):
                act_on_target(WindowTarget('Refusing app', executable='example.exe'), 'snap_right')
        self.assertTrue(native.closed)
        self.assertEqual(native.moves[-1], (100, 100, 1000, 800))
        native = FakeWindows()
        with patch('cairo.integrations.window_layout.Windows', return_value=native):
            with self.assertRaises(ValueError):
                act_on_target(WindowTarget('Example'), 'snap_top', monitor=3)
        self.assertEqual(native.moves, [])

    def test_discovered_store_app_uses_identity_not_title_matching(self):
        target = WindowTarget('Store App', app_id='Example.Package!App')
        with patch('cairo.integrations.app_discovery.find_app', return_value=record('Store App', 'Example.Package!App', 'appsfolder')), patch('cairo.integrations.app_discovery.window_identity', return_value=target), patch('cairo.integrations.window_layout.act_on_target', return_value={"message":"done"}) as position:
            DesktopController(True, discover_apps=True).window_action('Store App', 'snap_top', monitor=2)
        position.assert_called_once_with(target, 'snap_top', monitor=2)
        with patch.dict('sys.modules', {'win32com.client': None}):
            identity = window_identity(record('Store App', 'Example.Package!App', 'appsfolder'))
        self.assertEqual(identity.app_id, 'Example.Package!App')
        self.assertEqual(identity.executable, '')

    def test_numeric_tool_arguments_and_ui_permission_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = Orchestrator(Settings(workspace=root/'work', data_dir=root/'data', allow_desktop=True))
            try:
                sid = app.memory.create_session()['id']
                args = {'app':'chrome', 'action':'custom', 'x':100, 'y':80, 'width':900, 'height':600, 'monitor':1}
                with patch.object(app.tools.desktop, 'window_action', return_value={"message":"positioned"}) as action:
                    self.assertTrue(json.loads(app.tools.execute('window_action', args, 'SystemAgent', sid, allow_ui_actions=True))['ok'])
                    self.assertFalse(json.loads(app.tools.execute('window_action', {**args, 'x':True}, 'SystemAgent', sid, allow_ui_actions=True))['ok'])
                    self.assertFalse(json.loads(app.tools.execute('window_action', args, 'SystemAgent', sid, allow_ui_actions=False))['ok'])
                    action.assert_called_once_with(**args)
            finally:
                app.close()
