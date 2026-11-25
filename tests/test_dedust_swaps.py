"""Regressions for pool logs whose high-level TonAPI events omit JettonSwap."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import trades


class DeDustSwaps(unittest.TestCase):
    def setUp(self):
        self.tx = json.loads((Path(__file__).parent / "fixtures/dedust-swap.json").read_text())
        self.pool = trades.PRIMARY

    def parse(self, tx=None):
        return list(trades.dedust_rows(tx or self.tx, self.pool))

    def test_real_buy_uses_executed_amount_not_attached_gas(self):
        row, = self.parse()
        self.assertEqual(row["kind"], "buy")
        self.assertEqual(row["ton"], "1")
        self.assertEqual(row["tokenAmount"], "19786.577064266")
        self.assertEqual(row["tx"], self.tx["hash"])
        self.assertEqual(row["wallet"], self.tx["in_msg"]["decoded_body"]["sender_addr"])
        self.assertEqual(list(trades.swap_rows({"transaction": self.tx}, self.pool)), [row])

    def test_sell_direction_and_decimal_precision(self):
        body = self.tx["out_msgs"][0]["decoded_body"]
        body["asset_in"], body["asset_out"] = body["asset_out"], body["asset_in"]
        body["amount_in"], body["amount_out"] = "12345000000000", "7654321000"
        row, = self.parse()
        self.assertEqual((row["kind"], row["tokenAmount"], row["ton"]), ("sell", "12345", "7.654321"))

    def test_failed_bounced_and_non_swap_transactions_are_not_trades(self):
        for change in ("failed", "aborted", "bounced", "no-log"):
            tx = copy.deepcopy(self.tx)
            if change == "failed": tx["success"] = False
            elif change == "aborted": tx["aborted"] = True
            elif change == "bounced": tx["in_msg"]["bounced"] = True
            else: tx["out_msgs"] = []
            self.assertEqual(self.parse(tx), [])

    def test_wrong_pool_token_emitter_zero_and_missing_decode_rejected(self):
        for change in ("pool", "token", "emitter", "zero", "decode", "duplicate"):
            tx = copy.deepcopy(self.tx)
            log = tx["out_msgs"][0]
            if change == "pool": tx["account"]["address"] = "0:" + "a"*64
            elif change == "token": log["decoded_body"]["asset_out"]["jetton"]["address"] = "a"*64
            elif change == "emitter": log["source"]["address"] = "0:" + "b"*64
            elif change == "zero": log["decoded_body"]["amount_out"] = "0"
            elif change == "decode": del log["decoded_body"]
            else: tx["out_msgs"].append(copy.deepcopy(log))
            with self.assertRaises((ValueError, KeyError), msg=change): self.parse(tx)

    def test_transaction_pagination_is_shared_by_live_and_history(self):
        with patch.object(trades, "fetch", return_value={"transactions": [self.tx]}) as fetch:
            page = trades.pool_page(self.pool, {"limit": 1, "before_lt": self.tx["lt"]+1})
        self.assertIn("/blockchain/accounts/", fetch.call_args.args[0])
        self.assertEqual(page["next_from"], self.tx["lt"])
        self.assertEqual(page["events"][0]["timestamp"], self.tx["utime"])
        with patch.object(trades, "fetch", return_value={"transactions": []}):
            self.assertEqual(trades.pool_page(self.pool, {"limit": 100})["next_from"], 0)

    def test_failed_page_never_returns_a_partial_live_section(self):
        previous = {"asOf": self.tx["utime"]-60, "since": self.tx["utime"]-86400, "rows": []}
        before = copy.deepcopy(previous)
        with patch.object(trades, "pool_page", side_effect=OSError("offline")):
            with self.assertRaises(OSError): trades.collect(previous, 1, self.tx["utime"]+60)
        self.assertEqual(previous, before)


if __name__ == "__main__":
    unittest.main()
