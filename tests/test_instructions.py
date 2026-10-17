import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from instructions import Instruction, InstructionStore, check_instructions, parse_instructions


class InstructionTests(unittest.TestCase):
    def test_global_catalog_suppresses_baseline_and_existing_entries(self):
        entries = [Instruction('A', 'Existing', 'https://example.com/a'),
                   Instruction('B', 'New', 'https://example.com/b')]
        for baseline, expected in [(True, []), (False, [entries[1]])]:
            connection = Mock()
            connection.__enter__ = Mock(return_value=connection)
            connection.__exit__ = Mock(return_value=False)
            cursor = Mock()
            cursor.__enter__ = Mock(return_value=cursor)
            cursor.__exit__ = Mock(return_value=False)
            cursor.fetchone.return_value = None if baseline else (1,)
            connection.cursor.return_value = cursor
            def execute(query, parameters=None):
                cursor.rowcount = 0 if parameters and parameters[0] == 'A' else 1
            cursor.execute.side_effect = execute
            store = InstructionStore(lambda: connection)
            store._initialized = True
            self.assertEqual(store.discover(entries), expected)
            connection.commit.assert_called_once()

    def test_parser_validates_and_deduplicates_cards(self):
        card = '<div><p>Quest Title</p><p>Avalon Hill (F1234)</p><p>English</p><a href="/details/quest">View Details</a></div>'
        result = parse_instructions('<a href="/incomplete">View Details</a>' + card + card)
        self.assertEqual(result, [Instruction('F1234', 'Quest Title', 'https://instructions.hasbro.com/details/quest')])
        self.assertEqual(parse_instructions(card.replace('/details/quest', 'https://example.com/quest')), [])
        self.assertEqual(parse_instructions(card.replace('(F1234)', 'Unknown ID')), [])

    def test_incompatible_existing_table_is_not_modified(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = [('unknown_column',)]
        store = InstructionStore(lambda: connection)
        with self.assertRaisesRegex(RuntimeError, 'schema needs review'):
            store.initialize()
        queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any('ALTER' in query or 'DROP' in query or 'DELETE' in query for query in queries))
        self.assertFalse(store._initialized)


class AnnouncementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = Instruction('F1234', 'Quest Title', 'https://instructions.hasbro.com/details/quest')
        self.channel = SimpleNamespace(id=123, send=AsyncMock())
        self.store = Mock()
        self.store.was_sent.return_value = False
        self.store.discover.return_value = [self.entry]

    async def run_check(self, directory=None):
        with patch('instructions.fetch_instructions', return_value=[self.entry]):
            await check_instructions(self.channel, self.store, directory)

    async def test_new_channel_with_no_new_global_discoveries_stays_silent(self):
        self.store.discover.return_value = []
        await self.run_check()
        self.channel.send.assert_not_awaited()
        self.store.reserve.assert_not_called()

    async def test_new_discovery_is_shared_with_all_current_destinations(self):
        second = SimpleNamespace(id=456, send=AsyncMock())
        for channel in [self.channel, second]:
            await check_instructions(channel, self.store, entries=[self.entry])
            channel.send.assert_awaited_once()
        self.store.discover.assert_not_called()

    async def test_new_instruction_is_recorded_after_send(self):
        self.channel.send.side_effect = lambda *args, **kwargs: self.assertTrue(self.store.reserve.called)
        await self.run_check()
        self.channel.send.assert_awaited_once()
        self.store.finish.assert_called_once_with(123, self.entry)

    async def test_already_sent_instruction_is_skipped(self):
        self.store.was_sent.return_value = True
        await self.run_check()
        self.channel.send.assert_not_awaited()
        self.store.record_sent.assert_not_called()

    async def test_failed_send_remains_retryable(self):
        self.channel.send.side_effect = RuntimeError('Discord unavailable')
        with self.assertRaises(RuntimeError):
            await self.run_check()
        self.store.record_sent.assert_not_called()

    async def test_local_history_is_imported_without_resending(self):
        for name in ['F1234.txt', 'Quest Title.txt']:
            self.store.reset_mock()
            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / name).write_text('processed')
                await self.run_check(directory)
            self.channel.send.assert_not_awaited()
            self.store.record_sent.assert_called_once_with(123, self.entry)
