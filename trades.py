"""Successful direct TON/JSI swaps from tracked pool events."""
import re
import time
from urllib.parse import urlencode

from assets import MASTER_RAW, fetch, raw_address, token_amount, native_amount
from scripts.project_runtime import canonical_address

PRIMARY = 'EQBLX8vWiUk8noyQEUy6ovLokfK6ToP_IVM5aVyaqRuxOQ7I'
POOLS = {'EQBLX8vWiUk8noyQEUy6ovLokfK6ToP_IVM5aVyaqRuxOQ7I': ('dedust', 'DeDust')}
TX_HASH = re.compile(r"[a-f0-9]{64}")


def swap_rows(event, pool):
    if "transaction" in event:
        yield from dedust_rows(event["transaction"], pool)
        return
    if event["in_progress"]:
        return
    dex, label = POOLS[pool]
    for action in event["actions"]:
        if action["type"] != "JettonSwap" or action["status"] != "ok":
            continue
        swap = action["JettonSwap"]
        if swap["dex"] != dex:
            continue
        source = (swap.get("jetton_master_in") or {}).get("address")
        target = (swap.get("jetton_master_out") or {}).get("address")
        if target == MASTER_RAW and source is None and swap.get("ton_in"):
            kind, jetton, gram = "buy", swap["amount_out"], swap["ton_in"]
        elif source == MASTER_RAW and target is None and swap.get("ton_out"):
            kind, jetton, gram = "sell", swap["amount_in"], swap["ton_out"]
        else:
            continue
        # The action's first underlying transaction also distinguishes actions in one trace.
        tx = action["base_transactions"][0]
        if not TX_HASH.fullmatch(tx):
            raise ValueError("Invalid swap transaction hash")
        jetton, gram = token_amount(jetton), native_amount(gram)
        if jetton != "0" and gram != "0":
            yield {"kind": kind, "time": int(event["timestamp"]), "tx": tx,
                   "lt": str(event["lt"]), "wallet": raw_address(swap["user_wallet"]["address"]),
                   "tokenAmount": jetton, "ton": gram, "dex": label, "pool": pool}


def dedust_rows(transaction, pool):
    """Read the pool's own swap log, rather than TonAPI's trace classifier.

    https://docs.dedust.io/reference/tlb-schemes#event-swap
    The amounts are executed pool amounts, excluding attached gas. The sender
    is the swap initiator; it may itself be a router/contract.
    """
    address = canonical_address(pool)
    if raw_address(transaction["account"]["address"]) != address:
        raise ValueError("Transaction belongs to another pool")
    if not transaction["success"] or transaction.get("aborted", False):
        return
    incoming = transaction.get("in_msg") or {}
    if incoming.get("bounced"):
        return
    logs = [m for m in transaction["out_msgs"]
            if m.get("msg_type") == "ext_out_msg" and m.get("op_code") == "0x9c610de3"]
    if len(logs) > 1:
        raise ValueError("Ambiguous multiple swaps in one pool transaction")
    for message in logs:
        if raw_address(message["source"]["address"]) != address:
            raise ValueError("Swap log is not emitted by configured pool")
        body = message["decoded_body"]

        def asset(value):
            if value["sum_type"] == "Native":
                return "TON"
            if value["sum_type"] == "Jetton":
                jetton = value["jetton"]
                return raw_address(f'{int(jetton["workchain_id"])}:{jetton["address"]}')
            raise ValueError("Unsupported asset in configured TON/JSI pool")

        pair = asset(body["asset_in"]), asset(body["asset_out"])
        if pair == ("TON", MASTER_RAW):
            kind, jetton, gram = "buy", body["amount_out"], body["amount_in"]
        elif pair == (MASTER_RAW, "TON"):
            kind, jetton, gram = "sell", body["amount_in"], body["amount_out"]
        else:
            raise ValueError("Swap log assets do not match configured TON/JSI pair")
        tx = transaction["hash"]
        if not TX_HASH.fullmatch(tx):
            raise ValueError("Invalid pool transaction hash")
        jetton, gram = token_amount(jetton), native_amount(gram)
        if jetton == "0" or gram == "0":
            raise ValueError("Nonpositive executed swap amount")
        yield {"kind": kind, "time": int(transaction["utime"]), "tx": tx,
               "lt": str(transaction["lt"]),
               "wallet": raw_address(body["field4"]["sender_addr"]),
               "tokenAmount": jetton, "ton": gram, "dex": POOLS[pool][1],
               "pool": pool, "source": "dedust_pool_swap_log"}


def pool_page(pool, params):
    """Present transaction logs in the same page shape as indexed events."""
    if POOLS[pool][0] != "dedust":
        return fetch(f"/accounts/{pool}/events?" + urlencode(params))
    transactions = fetch(f"/blockchain/accounts/{pool}/transactions?" + urlencode(params))["transactions"]
    events = []
    for tx in transactions:
        if int(tx["lt"]) <= 0 or int(tx["utime"]) <= 0:
            raise ValueError("Invalid pool transaction position")
        events.append({"timestamp": int(tx["utime"]), "lt": str(tx["lt"]),
                       "in_progress": False, "transaction": tx})
    cursor = min((int(e["lt"]) for e in events), default=0)
    return {"events": events, "next_from": cursor if len(events) == params.get("limit", 100) else 0}


def collect_pool(pool, start, end, max_pages):
    rows = {}
    before = None
    for _ in range(max_pages):
        params = {"limit": 100}
        if before is not None:
            params["before_lt"] = before
        page = pool_page(pool, params)
        events = page["events"]
        for event in events:
            if start <= event["timestamp"] <= end:
                for row in swap_rows(event, pool):
                    rows[row["tx"]] = row
        if not events or min(e["timestamp"] for e in events) < start:
            return rows, start
        cursor = int(page["next_from"])
        if not cursor:
            return rows, start
        if before is not None and cursor >= before:
            raise ValueError("Pool event cursor did not advance")
        before = cursor
        time.sleep(1)
    raise RuntimeError(f"Pool history page limit reached: {pool}")


def collect(previous, cutoff, now, max_pages=180):
    # Bootstrap a bounded recent window; the separate backfill extends it.
    start = max(cutoff, previous["asOf"] - 6 * 3600) if previous.get("asOf") else max(cutoff, now - 86400)
    rows = {row["tx"]: row for row in previous.get("rows", []) if cutoff <= row["time"] < start}
    for pool in POOLS:
        fresh, _ = collect_pool(pool, start, now, max_pages)
        for tx, row in fresh.items():
            if tx not in rows or pool == PRIMARY:
                rows[tx] = row
    since = max(cutoff, min(start, previous.get("since", start)))
    return {"rows": sorted(rows.values(), key=lambda r: (r["time"], int(r["lt"]), r["tx"]), reverse=True),
            "since": since, "asOf": now}


def rates():
    data = fetch("/coins/the-open-network/market_chart?vs_currency=usd&days=365",
                 api="https://api.coingecko.com/api/v3")
    # CoinGecko returns daily closes at UTC boundaries and a final intraday quote.
    prices = [[int(ms) // 1000, float(usd)] for ms, usd in data["prices"]]
    if len(prices) < 2 or any(not 0 < price < 1000 for _, price in prices):
        raise ValueError("Invalid TON/USD history")
    return sorted(prices)
