import unittest
from unittest.mock import Mock, patch

import requests
from roll_services import test_dddice_connection as connection_test


class ConnectionTests(unittest.TestCase):
    def test_success_uses_only_read_requests(self):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = {'data': {}}
        with patch('roll_services.integration_key', return_value='private-key'), \
             patch('roll_services.requests.get', return_value=response) as get, \
             patch('roll_services.requests.post') as post:
            result = connection_test({'destination': 'test-room'})
        self.assertIn('Connection successful', result)
        self.assertEqual(get.call_count, 2)
        self.assertTrue(get.call_args.args[0].endswith('/room/test-room'))
        post.assert_not_called()
        self.assertNotIn('private-key', result)

    def test_auth_failure_and_timeout_have_safe_messages(self):
        with patch('roll_services.integration_key', return_value='private-key'):
            with patch('roll_services.requests.get', return_value=Mock(status_code=401)):
                self.assertIn('key rejected', connection_test({}))
            with patch('roll_services.requests.get', side_effect=requests.Timeout('private-key')):
                result = connection_test({})
                self.assertIn('timed out', result)
                self.assertNotIn('private-key', result)

    def test_missing_room_reports_partial_success(self):
        response = Mock(status_code=200, ok=True)
        response.json.return_value = {'data': []}
        with patch('roll_services.integration_key', return_value='private-key'), \
             patch('roll_services.requests.get', return_value=response):
            self.assertIn('No room configured', connection_test({}))
