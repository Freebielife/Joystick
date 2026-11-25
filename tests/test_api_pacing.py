"""Keyless TonAPI requests share the stricter published rate budget."""
import unittest
from unittest.mock import patch
import assets


class ApiPacing(unittest.TestCase):
    def setUp(self):
        assets._next_request.clear()

    def tearDown(self):
        assets._next_request.clear()

    def test_next_tonapi_request_waits_for_shared_budget(self):
        with patch.object(assets.time, 'monotonic', side_effect=[10, 10, 11, 14.2]), \
             patch.object(assets.time, 'sleep') as sleep:
            assets.pace(assets.API)
            assets.pace(assets.API)
        self.assertAlmostEqual(sleep.call_args.args[0], 3.2)
        self.assertAlmostEqual(assets._next_request[assets.API], 18.4)

    def test_external_rate_source_does_not_use_tonapi_budget(self):
        with patch.object(assets.time, 'sleep') as sleep:
            assets.pace('https://api.coingecko.com/api/v3')
        sleep.assert_not_called()
        self.assertEqual(assets._next_request, {})
