"""The public network: everything an outside observer could see.

This is the ONLY data the detection engine receives. It holds accounts,
wallets, the transfer ledger, posts, actions and governance proposals.
Hidden simulation parameters (personas, rhythms, operator plans) and the
ground-truth labels live in ``mirage.sim`` and are never referenced from
here; ``tests/test_label_leak.py`` enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from .util import GrowableArray


class EventKind(IntEnum):
    JOIN = 0
    POST = 1
    REPLY = 2
    FOLLOW = 3
    TRANSFER = 4
    VOTE = 5
    PROPOSE = 6


ACTION_KINDS = (EventKind.POST, EventKind.REPLY, EventKind.FOLLOW, EventKind.TRANSFER, EventKind.VOTE)


@dataclass
class Proposal:
    id: int
    title: str
    created_at: float
    closes_at: float
    proposer: int
    recipient: str = ""
    amount: float = 0.0

    def is_open(self, t: float) -> bool:
        return self.created_at <= t < self.closes_at


class NetworkState:
    """Append-only public record of the network.

    Times are simulated minutes since the start of the simulation; accounts
    that pre-date the simulation have negative creation times.
    """

    def __init__(self) -> None:
        # accounts
        self.acct_created = GrowableArray(np.float64)
        self.acct_wallet = GrowableArray(np.int32)
        self.handles: list[str] = []
        # wallets (account wallets plus any other address that moved funds)
        self.wallet_addr: list[str] = []
        self.wallet_owner = GrowableArray(np.int32)
        # public labels for well-known service wallets (exchange hot wallets),
        # the way block explorers label them. None for everything else.
        self.wallet_label: list[str | None] = []
        # ledger
        self.tx_t = GrowableArray(np.float64)
        self.tx_src = GrowableArray(np.int32)
        self.tx_dst = GrowableArray(np.int32)
        self.tx_amount = GrowableArray(np.float64)
        # posts
        self.post_t = GrowableArray(np.float64)
        self.post_author = GrowableArray(np.int32)
        self.post_parent = GrowableArray(np.int64)
        self.post_text: list[str] = []
        # action log
        self.ev_t = GrowableArray(np.float64)
        self.ev_kind = GrowableArray(np.int8)
        self.ev_actor = GrowableArray(np.int32)
        self.ev_obj = GrowableArray(np.int64)
        self.ev_aux = GrowableArray(np.int64)
        # governance
        self.proposals: dict[int, Proposal] = {}
        self.treasury: float = 1_250_000.0
        self.now: float = 0.0

    # ------------------------------------------------------------ sizes
    @property
    def n_accounts(self) -> int:
        return self.acct_created.n

    @property
    def n_events(self) -> int:
        return self.ev_t.n

    @property
    def n_posts(self) -> int:
        return self.post_t.n

    @property
    def n_wallets(self) -> int:
        return len(self.wallet_addr)

    # ------------------------------------------------------------ writers
    def add_wallet(self, addr: str, owner: int = -1, label: str | None = None) -> int:
        self.wallet_addr.append(addr)
        self.wallet_owner.append(owner)
        self.wallet_label.append(label)
        return len(self.wallet_addr) - 1

    def add_account(self, created_at: float, handle: str, wallet_addr: str) -> int:
        idx = self.acct_created.n
        wallet = self.add_wallet(wallet_addr, owner=idx)
        self.acct_created.append(created_at)
        self.acct_wallet.append(wallet)
        self.handles.append(handle)
        self.add_event(created_at, EventKind.JOIN, idx, idx)
        return idx

    def add_transfer(self, t: float, src: int, dst: int, amount: float) -> int:
        row = self.tx_t.append(t)
        self.tx_src.append(src)
        self.tx_dst.append(dst)
        self.tx_amount.append(amount)
        owner = int(self.wallet_owner[src])
        if owner >= 0:
            self.add_event(t, EventKind.TRANSFER, owner, row, dst)
        return row

    def add_post(self, t: float, author: int, text: str, parent: int = -1) -> int:
        pid = self.post_t.append(t)
        self.post_author.append(author)
        self.post_parent.append(parent)
        self.post_text.append(text)
        if parent >= 0:
            self.add_event(t, EventKind.REPLY, author, pid, parent)
        else:
            self.add_event(t, EventKind.POST, author, pid)
        return pid

    def add_event(self, t: float, kind: int, actor: int, obj: int = -1, aux: int = -1) -> int:
        row = self.ev_t.append(t)
        self.ev_kind.append(kind)
        self.ev_actor.append(actor)
        self.ev_obj.append(obj)
        self.ev_aux.append(aux)
        return row

    def add_proposal(self, proposal: Proposal) -> None:
        self.proposals[proposal.id] = proposal
        self.add_event(proposal.created_at, EventKind.PROPOSE, proposal.proposer, proposal.id)

    def add_vote(self, t: float, voter: int, proposal_id: int, choice: int) -> int:
        return self.add_event(t, EventKind.VOTE, voter, proposal_id, choice)

    # ------------------------------------------------------------ readers
    def votes(self, proposal_id: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(voters, choices, times) for a proposal; first vote per account wins."""
        kind = self.ev_kind.a
        mask = (kind == EventKind.VOTE) & (self.ev_obj.a == proposal_id)
        voters = self.ev_actor.a[mask]
        choices = self.ev_aux.a[mask]
        times = self.ev_t.a[mask]
        _, first = np.unique(voters, return_index=True)
        first.sort()
        return voters[first], choices[first], times[first]

    def open_proposals(self, t: float | None = None) -> list[Proposal]:
        t = self.now if t is None else t
        return [p for p in self.proposals.values() if p.is_open(t)]
