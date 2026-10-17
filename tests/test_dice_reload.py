import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import boardgamedice as board
import commands


class ReloadTests(unittest.TestCase):
    def test_changed_alias_updates_dispatch_and_help_invalid_edit_preserves_it(self):
        original = dict(board.dice_sets)
        original_source = board._loaded_source
        registry = commands.dice_sets
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'dice.json'
                updated = json.loads(original_source)
                updated['hqdice']['diceTypes']['pink']['aliases'] = ['rose']
                path.write_text(json.dumps(updated), encoding='utf-8')
                with patch.object(board, 'DICE_FILE', path):
                    self.assertTrue(board.reload_dice_sets())
                    self.assertIs(commands.dice_sets, registry)
                    self.assertEqual(board.parse_dice('hqroll', '2 rose')[1], {'pink': 2})
                    self.assertIn('rose', board.generate_help('hqroll'))
                    self.assertFalse(board.reload_dice_sets())
                    for source in ['{', json.dumps({'hqdice': {}})]:
                        path.write_text(source, encoding='utf-8')
                        with self.assertRaises((ValueError, KeyError)):
                            board.reload_dice_sets()
                        self.assertEqual(board.parse_dice('hqroll', '2 rose')[1], {'pink': 2})
        finally:
            board.dice_sets.clear()
            board.dice_sets.update(original)
            board._loaded_source = original_source
