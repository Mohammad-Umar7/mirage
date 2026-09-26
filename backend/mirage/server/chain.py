"""Bridge to the local chain: relayer + detection oracle.

* Relayer: registers simulated accounts and relays every vote the network
  casts, each signed by that account's own (deterministic, local-only) key.
* Oracle: when the set of flagged clusters changes, posts a signed epoch of
  cluster assignments (begin -> member chunks -> finalize).
* Reads back both tallies (one-account-one-vote and correlation-weighted)
  straight from the contract and publishes them with the tx hashes.

The keys below are Hardhat's publicly known development keys. They exist
only on a local chain and must never hold anything of value.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from eth_abi import encode as abi_encode
from eth_keys import keys
from eth_utils import keccak, to_checksum_address

from ..config import REPO_ROOT
from ..network import EventKind

DEPLOYMENT = REPO_ROOT / "deployments" / "local.json"
# Hardhat default accounts #0 (relayer) and #1 (oracle). Public test keys.
DEV_RELAYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEV_ORACLE_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
WAD = 10**18
# Nodes enforce a per-transaction gas cap of 2**24 (EIP-7825), so batches stay
# comfortably under ~15M gas.
TX_GAS = 15_500_000
REGISTER_CHUNK = 450
VOTE_CHUNK = 250
MEMBER_CHUNK = 280


def _personal_sign(key: keys.PrivateKey, digest: bytes) -> bytes:
    h = keccak(b"\x19Ethereum Signed Message:\n32" + digest)
    sig = key.sign_msg_hash(h)
    return sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 27])


class AccountKeys:
    """Deterministic per-account keys (local simulation only)."""

    def __init__(self) -> None:
        self._keys: list[keys.PrivateKey] = []
        self._addrs: list[str] = []

    def ensure(self, n: int) -> None:
        for i in range(len(self._keys), n):
            k = keys.PrivateKey(keccak(b"mirage-account-" + i.to_bytes(8, "big")))
            self._keys.append(k)
            self._addrs.append(k.public_key.to_checksum_address())

    def key(self, i: int) -> keys.PrivateKey:
        self.ensure(i + 1)
        return self._keys[i]

    def addr(self, i: int) -> str:
        self.ensure(i + 1)
        return self._addrs[i]


class ChainBridge:
    def __init__(self, deployment: dict, publish, flag_threshold: float = 0.8) -> None:
        from web3 import Web3

        self.dep = deployment
        self.publish = publish
        self.flag_threshold = flag_threshold
        self.rpc = deployment.get("rpc", "http://127.0.0.1:8545")
        self.w3 = Web3(Web3.HTTPProvider(self.rpc, request_kwargs={"timeout": 20}))
        self.address = to_checksum_address(deployment["address"])
        self.gov = self.w3.eth.contract(address=self.address, abi=deployment["abi"])
        self.relayer_key = keys.PrivateKey(bytes.fromhex(os.environ.get("MIRAGE_RELAYER_KEY", DEV_RELAYER_KEY)[2:]))
        self.oracle_key = keys.PrivateKey(bytes.fromhex(os.environ.get("MIRAGE_ORACLE_KEY", DEV_ORACLE_KEY)[2:]))
        self.relayer_addr = self.relayer_key.public_key.to_checksum_address()
        self.chain_id = int(deployment.get("chainId", 31337))
        self.accounts = AccountKeys()
        self.jobs: queue.Queue = queue.Queue()
        self.txs: deque[dict] = deque(maxlen=40)
        self.onchain: dict[str, dict] = {}
        self.connected = False
        self.error: str | None = None
        self.block: int | None = None
        self.mode = deployment.get("mode", "one")
        self.world = 0
        self.session = int(time.time()) % 1_000_000
        self._registered = 0
        self._created: set[int] = set()
        self._vote_cursor = 0
        self._last_flagged: tuple = ()
        self._last_attest_at = 0.0
        self._epoch = 0
        self._nonce: int | None = None
        self._stop = threading.Event()
        self._pending_attest = None
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, name="mirage-chain", daemon=True).start()

    @classmethod
    def from_env(cls, publish) -> "ChainBridge":
        path = Path(os.environ.get("MIRAGE_DEPLOYMENT", DEPLOYMENT))
        if not path.exists():
            raise FileNotFoundError(f"{path} not found (deploy the contract first: npm run chain)")
        return cls(json.loads(path.read_text(encoding="utf-8")), publish)

    def stop(self) -> None:
        self._stop.set()

    # ---------------------------------------------------------- runtime API
    def pid_base(self) -> int:
        """On-chain proposal ids are namespaced per process session and per
        world, so neither a reset nor a backend restart collides with old votes."""
        return (self.session * 1000 + self.world) * 1000

    def chain_pid(self, pid: int) -> int:
        return self.pid_base() + pid

    def on_reset(self, world: int) -> None:
        # the vote cursor is owned by the runtime thread (on_tick), so reset it here
        self._vote_cursor = 0
        self._last_flagged = ()
        with self._lock:
            self._pending_attest = None
        self.jobs.put(("reset", world))

    def on_tick(self, net) -> None:
        """Snapshot what is new since the last tick (runs in the runtime thread)."""
        n_acc = net.n_accounts
        props = [(p.id, p.title, p.recipient, p.amount, p.created_at, p.closes_at) for p in net.proposals.values()
                 if p.id >= 5]
        end = net.n_events
        start = self._vote_cursor
        votes = []
        if end > start:
            kinds = net.ev_kind.a[start:end]
            idx = np.flatnonzero(kinds == EventKind.VOTE)
            if len(idx):
                voters = net.ev_actor.a[start:end][idx]
                pids = net.ev_obj.a[start:end][idx]
                choices = net.ev_aux.a[start:end][idx]
                votes = list(zip(voters.tolist(), pids.tolist(), choices.tolist()))
            self._vote_cursor = end
        self.jobs.put(("sync", n_acc, props, votes))

    def on_detection(self, result, net) -> None:
        flagged = [(c.id, c.members.copy()) for c in result.clusters
                   if c.verdict == "SWARM" and c.confidence >= self.flag_threshold]
        signature = tuple(sorted((cid, len(m) // 25) for cid, m in flagged))
        if signature == self._last_flagged:
            return
        self._last_flagged = signature
        with self._lock:
            self._pending_attest = flagged  # coalesce: only the newest picture matters

    def info(self) -> dict:
        return {
            "connected": self.connected, "rpc": self.rpc, "chain_id": self.chain_id, "address": self.address,
            "oracle": self.oracle_key.public_key.to_checksum_address(), "block": self.block, "mode": self.mode,
            "txs": list(self.txs), "onchain": self.onchain, "error": self.error, "world": self.world,
            "pid_base": self.pid_base(),
        }

    # ------------------------------------------------------------- worker
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.connected:
                    self._connect()
                    if not self.connected:
                        time.sleep(2.0)
                        continue
                try:
                    job = self.jobs.get(timeout=0.5)
                except queue.Empty:
                    job = None
                if job is not None:
                    self._run(job)
                with self._lock:
                    attest, self._pending_attest = self._pending_attest, None
                if attest is not None:
                    self._attest(attest)
                if job is not None or attest is not None:
                    self._refresh()
            except Exception as exc:  # the chain is optional: log, back off, keep going
                self.connected = False
                self.error = str(exc)[:200]
                self._nonce = None
                print(f"[mirage.chain] {exc}")
                self.publish({"type": "chain", **self.info()}, None)
                time.sleep(2.0)

    def _connect(self) -> None:
        try:
            ok = self.w3.is_connected() and len(self.w3.eth.get_code(self.address)) > 0
        except Exception as exc:
            ok = False
            self.error = str(exc)[:200]
        self.connected = ok
        if ok:
            self.error = None
            self._nonce = None
            self._epoch = int(self.gov.functions.epoch().call())
            self.mode = "log" if int(self.gov.functions.mode().call()) == 1 else "one"
            self.publish({"type": "chain", **self.info()}, None)

    def _run(self, job) -> None:
        kind = job[0]
        if kind == "reset":
            self.world = job[1]
            self._created.clear()
            self.onchain = {}
            return
        _, n_acc, props, votes = job
        if n_acc > self._registered:
            self.accounts.ensure(n_acc)
            for s in range(self._registered, n_acc, REGISTER_CHUNK):
                chunk = [self.accounts.addr(i) for i in range(s, min(n_acc, s + REGISTER_CHUNK))]
                self._send(self.gov.functions.register(chunk), "register", f"{len(chunk):,} accounts")
            self._registered = n_acc
        for pid, title, recipient, amount, created, closes in props:
            if pid in self._created:
                continue
            rec = to_checksum_address(recipient) if recipient else "0x" + "00" * 20
            self._send(self.gov.functions.createProposal(self.chain_pid(pid), title[:120], rec, int(amount),
                                                         int(max(0, created)), int(max(0, closes))),
                       "proposal", f"#{pid} {title[:40]}")
            self._created.add(pid)
        by_pid: dict[int, list[tuple[int, int]]] = {}
        for voter, pid, choice in votes:
            if pid in self._created:
                by_pid.setdefault(pid, []).append((voter, choice))
        for pid, items in by_pid.items():
            cpid = self.chain_pid(pid)
            for s in range(0, len(items), VOTE_CHUNK):
                part = items[s:s + VOTE_CHUNK]
                addrs, choices, sigs = [], [], []
                for voter, choice in part:
                    c = 1 if choice == 1 else 2
                    addr = self.accounts.addr(voter)
                    digest = keccak(abi_encode(["address", "uint256", "string", "uint256", "address", "uint8"],
                                               [self.address, self.chain_id, "MIRAGE_VOTE", cpid, addr, c]))
                    addrs.append(addr)
                    choices.append(c)
                    sigs.append(_personal_sign(self.accounts.key(voter), digest))
                self._send(self.gov.functions.castVotes(cpid, addrs, choices, sigs), "votes",
                           f"#{pid} · {len(part):,} signed votes")

    def _attest(self, flagged: list[tuple[int, np.ndarray]]) -> None:
        if time.monotonic() - self._last_attest_at < 4.0 and flagged:
            time.sleep(max(0.0, 4.0 - (time.monotonic() - self._last_attest_at)))
        self._last_attest_at = time.monotonic()
        e = max(self._epoch, int(self.gov.functions.epoch().call()), int(self.gov.functions.pendingEpoch().call())) + 1
        ids = [int(cid) for cid, _ in flagged]
        sizes = [int(len(m)) for _, m in flagged]
        digest = keccak(abi_encode(["address", "uint256", "string", "uint256", "uint32[]", "uint32[]"],
                                   [self.address, self.chain_id, "MIRAGE_BEGIN", e, ids, sizes]))
        self._send(self.gov.functions.beginEpoch(e, ids, sizes, _personal_sign(self.oracle_key, digest)), "oracle",
                   f"epoch {e} · {len(ids)} flagged cluster{'s' if len(ids) != 1 else ''}")
        rows = [(self.accounts.addr(int(a)), int(cid)) for cid, members in flagged for a in members.tolist()]
        for chunk, s in enumerate(range(0, len(rows), MEMBER_CHUNK)):
            part = rows[s:s + MEMBER_CHUNK]
            members = [r[0] for r in part]
            mids = [r[1] for r in part]
            digest = keccak(abi_encode(["address", "uint256", "string", "uint256", "uint256", "address[]", "uint32[]"],
                                       [self.address, self.chain_id, "MIRAGE_MEMBERS", e, chunk, members, mids]))
            self._send(self.gov.functions.attestMembers(e, chunk, members, mids, _personal_sign(self.oracle_key, digest)),
                       "attest", f"epoch {e} · {len(part):,} members")
        digest = keccak(abi_encode(["address", "uint256", "string", "uint256"], [self.address, self.chain_id, "MIRAGE_FINALIZE", e]))
        self._send(self.gov.functions.finalizeEpoch(e, _personal_sign(self.oracle_key, digest)), "oracle",
                   f"epoch {e} final · {sum(sizes):,} accounts share fate")
        self._epoch = e

    def _send(self, fn, kind: str, detail: str) -> None:
        if self._nonce is None:
            self._nonce = self.w3.eth.get_transaction_count(self.relayer_addr, "pending")
        gas_price = int(self.w3.eth.gas_price * 2)
        tx = fn.build_transaction({"from": self.relayer_addr, "nonce": self._nonce, "chainId": self.chain_id,
                                   "gas": TX_GAS, "gasPrice": gas_price})
        signed = self.w3.eth.account.sign_transaction(tx, self.relayer_key.to_hex())
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        h = self.w3.eth.send_raw_transaction(raw)
        self._nonce += 1
        receipt = self.w3.eth.wait_for_transaction_receipt(h, timeout=30)
        self.block = int(receipt["blockNumber"])
        self.txs.appendleft({"hash": h.hex() if isinstance(h, bytes) else str(h), "kind": kind, "detail": detail,
                             "block": self.block, "status": int(receipt["status"]), "gas": int(receipt["gasUsed"]),
                             "t": time.time()})

    def _refresh(self) -> None:
        out = {}
        for pid in sorted(self._created):
            cpid = self.chain_pid(pid)
            ny, nn = self.gov.functions.tally(cpid, False).call()
            wy, wn = self.gov.functions.tally(cpid, True).call()
            out[str(pid)] = {"naive": {"yes": ny / WAD, "no": nn / WAD}, "weighted": {"yes": wy / WAD, "no": wn / WAD},
                             "epoch": self._epoch}
        self.onchain = out
        self.block = int(self.w3.eth.block_number)
        self.publish({"type": "chain", **self.info()}, None)
