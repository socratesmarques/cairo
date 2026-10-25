from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cairo.memory import Memory
from cairo.scheduler.reminders import Reminders
from cairo.tools import ToolRegistry
from cairo.orchestrator.desktop_commands import parse_desktop_commands


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.memory = Memory(self.root / 'data/cairo.db')
        self.sid = self.memory.create_session()['id']
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.tools = ToolRegistry(self.workspace, self.memory, True, True)

    def call(self, name, args, agent='MasterAgent'):
        return json.loads(self.tools.execute(name, args, agent, self.sid))

    def test_reminders_persist_and_are_session_scoped(self):
        agenda = Reminders(self.memory)
        due = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        item = agenda.create(self.sid, 'Pausa', due)
        other = self.memory.create_session()['id']
        self.assertEqual(Reminders(Memory(self.memory.path)).list(self.sid)[0]['text'], 'Pausa')
        self.assertEqual(agenda.list(other), [])
        with self.assertRaises(KeyError):
            agenda.dismiss(item['id'], other)
        agenda.dismiss(item['id'], self.sid)
        self.assertEqual(agenda.list(), [])

    def test_reminder_validation(self):
        agenda = Reminders(self.memory)
        for due in ('bad', '2030-01-01T10:00:00', '2000-01-01T10:00:00+00:00'):
            with self.assertRaises(ValueError):
                agenda.create(self.sid, 'Pausa', due)
        self.assertFalse(self.call('reminder_create', {'text': 'x', 'due': 'bad'})['ok'])
        self.assertFalse(self.call('reminder_list', {}, 'ResearchAgent')['ok'])

    def test_search_and_directory_permissions(self):
        self.assertTrue(self.call('create_directory', {'path': 'project/sub'})['ok'])
        (self.workspace / 'project/sub/hello.txt').write_text('Cairo\nUseful evidence', encoding='utf-8')
        result = self.call('search_files', {'query': 'evidence', 'content': True})['result']
        self.assertEqual(result['matches'][0]['line'], 2)
        self.assertEqual(self.call('search_files', {'query': 'HELLO'})['result']['matches'][0]['path'], 'project/sub/hello.txt')
        self.assertFalse(self.call('search_files', {'query':'x','path':'../data'})['ok'])
        self.tools.policy.allow_write = False
        self.assertFalse(self.call('create_directory', {'path':'denied'})['ok'])
        self.assertNotIn('create_directory', [s['function']['name'] for s in self.tools.schemas('MasterAgent')])

    def test_search_skips_links_and_large_files(self):
        (self.workspace / 'big.txt').write_bytes(b'hello' * 20000)
        result = self.call('search_files', {'query':'hello', 'content':True})['result']
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['skipped'], 1)
        try:
            (self.workspace / 'link').symlink_to(self.root / 'data', target_is_directory=True)
        except OSError:
            return
        self.assertEqual(self.call('search_files', {'query':'cairo.db'})['result']['matches'], [])

    def test_direct_commands(self):
        actions = parse_desktop_commands('Me lembre em 10 minutos de beber água')
        self.assertEqual(actions[0][0], 'reminder_create')
        self.assertEqual(actions[0][1]['text'], 'beber água')
        self.assertIsNone(parse_desktop_commands('Não me lembre em 10 minutos de beber água'))
        self.assertEqual(parse_desktop_commands('Pesquise clima no Google'), [('search_web', {'query':'clima'})])

    def test_web_search_dispatch_and_permissions(self):
        with patch.object(self.tools.desktop, '_launch', return_value={}) as launch:
            self.assertTrue(self.call('search_web', {'query':'música & café'})['ok'])
            self.assertIn('q=m%C3%BAsica+%26+caf%C3%A9', launch.call_args.args[1][0])
            self.tools.desktop.enabled = False
            self.assertFalse(self.call('search_web', {'query':'x'})['ok'])
            self.assertEqual(launch.call_count, 1)
