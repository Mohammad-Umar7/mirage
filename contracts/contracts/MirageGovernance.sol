// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title MirageGovernance
 * @notice Governance where coordinated accounts share fate.
 *
 * Accounts are registered by the network relayer and vote with their own
 * signatures (relayed gaslessly, in batches). An off-chain detection engine
 * acts as an ORACLE: it posts signed epochs of cluster assignments. A flagged
 * cluster of n accounts then carries a total voting weight of 1 (Mode.ONE) or
 * ln(n) (Mode.LOG), split evenly across its members; everyone else counts 1.
 *
 * Tallies are maintained incrementally (per proposal, per epoch, per cluster)
 * so a weighted tally costs O(clusters), not O(voters).
 *
 * TRUST ASSUMPTION: the oracle key is trusted to report clusters honestly.
 * The README ("Oracle trust") discusses decentralizing it: several independent
 * detectors, threshold signatures, and a dispute window before an epoch binds.
 */
contract MirageGovernance {
    uint256 private constant WAD = 1e18;
    uint256 private constant LN2_WAD = 693147180559945309;
    uint256 private constant HALF_ORDER = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    enum Mode {
        ONE,
        LOG
    }

    struct Proposal {
        string title;
        address recipient;
        uint256 amount;
        uint64 start;
        uint64 end;
        uint32 yes;
        uint32 no;
        bool exists;
    }

    address public immutable owner;
    address public oracle;
    address public relayer;
    Mode public mode;

    mapping(address => bool) public registered;
    uint256 public registeredCount;

    mapping(uint256 => Proposal) public proposals;
    uint256[] public proposalIds;
    mapping(uint256 => mapping(address => uint8)) public voteOf; // 1 = yes, 2 = no

    uint256 public epoch; // latest finalized attestation epoch (0 = none yet)
    uint256 public pendingEpoch; // epoch currently being attested
    mapping(uint256 => mapping(address => uint32)) public clusterOf; // epoch => account => cluster id
    mapping(uint256 => mapping(uint32 => uint32)) public clusterSize; // epoch => cluster => size
    mapping(uint256 => uint32[]) private _clusters; // epoch => flagged cluster ids
    // proposal => epoch => cluster => votes from members of that cluster
    mapping(uint256 => mapping(uint256 => mapping(uint32 => uint32))) public clusterYes;
    mapping(uint256 => mapping(uint256 => mapping(uint32 => uint32))) public clusterNo;

    event Registered(uint256 added, uint256 total);
    event ProposalCreated(uint256 indexed id, string title, address recipient, uint256 amount);
    event VotesCast(uint256 indexed id, uint256 accepted, uint32 yes, uint32 no);
    event EpochBegun(uint256 indexed epoch, uint256 clusters);
    event MembersAttested(uint256 indexed epoch, uint256 chunk, uint256 members);
    event EpochFinalized(uint256 indexed epoch);
    event ModeChanged(Mode mode);

    error NotOwner();
    error NotRelayer();
    error BadSignature();
    error BadEpoch();
    error UnknownProposal();
    error LengthMismatch();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyRelayer() {
        if (msg.sender != relayer) revert NotRelayer();
        _;
    }

    constructor(address oracle_, address relayer_, Mode mode_) {
        owner = msg.sender;
        oracle = oracle_;
        relayer = relayer_;
        mode = mode_;
    }

    function setMode(Mode m) external onlyOwner {
        mode = m;
        emit ModeChanged(m);
    }

    function setOracle(address o) external onlyOwner {
        oracle = o;
    }

    // ------------------------------------------------------------------
    // Registration and proposals (the relayer is the network's sequencer)

    function register(address[] calldata accounts) external onlyRelayer {
        uint256 added;
        for (uint256 i; i < accounts.length; ++i) {
            if (!registered[accounts[i]]) {
                registered[accounts[i]] = true;
                ++added;
            }
        }
        registeredCount += added;
        emit Registered(added, registeredCount);
    }

    function createProposal(
        uint256 id,
        string calldata title,
        address recipient,
        uint256 amount,
        uint64 start,
        uint64 end
    ) external onlyRelayer {
        Proposal storage p = proposals[id];
        if (p.exists) return; // idempotent
        p.title = title;
        p.recipient = recipient;
        p.amount = amount;
        p.start = start;
        p.end = end;
        p.exists = true;
        proposalIds.push(id);
        emit ProposalCreated(id, title, recipient, amount);
    }

    // ------------------------------------------------------------------
    // Votes: each signed by the voter, relayed in batches

    function voteDigest(uint256 id, address voter, uint8 choice) public view returns (bytes32) {
        return keccak256(abi.encode(address(this), block.chainid, "MIRAGE_VOTE", id, voter, choice));
    }

    function castVotes(
        uint256 id,
        address[] calldata voters,
        uint8[] calldata choices,
        bytes[] calldata sigs
    ) external onlyRelayer {
        if (voters.length != choices.length || voters.length != sigs.length) revert LengthMismatch();
        Proposal storage p = proposals[id];
        if (!p.exists) revert UnknownProposal();
        uint32 yes;
        uint32 no;
        uint256 accepted;
        uint256 e = epoch;
        uint256 pe = pendingEpoch;
        for (uint256 i; i < voters.length; ++i) {
            address v = voters[i];
            uint8 c = choices[i];
            if (!registered[v] || voteOf[id][v] != 0 || (c != 1 && c != 2)) continue;
            // a bad signature skips that vote; the rest of the batch still lands
            if (_recover(voteDigest(id, v, c), sigs[i]) != v) continue;
            voteOf[id][v] = c;
            if (c == 1) ++yes;
            else ++no;
            ++accepted;
            _countCluster(id, e, v, c);
            if (pe > e) _countCluster(id, pe, v, c);
        }
        p.yes += yes;
        p.no += no;
        emit VotesCast(id, accepted, yes, no);
    }

    function _countCluster(uint256 id, uint256 e, address v, uint8 c) private {
        if (e == 0) return;
        uint32 k = clusterOf[e][v];
        if (k == 0) return;
        if (c == 1) ++clusterYes[id][e][k];
        else ++clusterNo[id][e][k];
    }

    // ------------------------------------------------------------------
    // Oracle attestations: begin -> attest member chunks -> finalize

    function beginEpoch(uint256 e, uint32[] calldata clusterIds, uint32[] calldata sizes, bytes calldata sig) external {
        if (e <= epoch || e < pendingEpoch) revert BadEpoch();
        if (clusterIds.length != sizes.length) revert LengthMismatch();
        bytes32 digest = keccak256(abi.encode(address(this), block.chainid, "MIRAGE_BEGIN", e, clusterIds, sizes));
        if (_recover(digest, sig) != oracle) revert BadSignature();
        pendingEpoch = e;
        delete _clusters[e];
        for (uint256 i; i < clusterIds.length; ++i) {
            clusterSize[e][clusterIds[i]] = sizes[i];
            _clusters[e].push(clusterIds[i]);
        }
        emit EpochBegun(e, clusterIds.length);
    }

    function attestMembers(
        uint256 e,
        uint256 chunk,
        address[] calldata members,
        uint32[] calldata ids,
        bytes calldata sig
    ) external {
        if (e != pendingEpoch) revert BadEpoch();
        if (members.length != ids.length) revert LengthMismatch();
        bytes32 digest = keccak256(abi.encode(address(this), block.chainid, "MIRAGE_MEMBERS", e, chunk, members, ids));
        if (_recover(digest, sig) != oracle) revert BadSignature();
        uint256 np = proposalIds.length;
        for (uint256 i; i < members.length; ++i) {
            address m = members[i];
            uint32 k = ids[i];
            if (k == 0 || clusterOf[e][m] != 0) continue;
            clusterOf[e][m] = k;
            // fold in votes this account already cast
            for (uint256 j; j < np; ++j) {
                uint256 pid = proposalIds[j];
                uint8 c = voteOf[pid][m];
                if (c == 1) ++clusterYes[pid][e][k];
                else if (c == 2) ++clusterNo[pid][e][k];
            }
        }
        emit MembersAttested(e, chunk, members.length);
    }

    function finalizeEpoch(uint256 e, bytes calldata sig) external {
        if (e != pendingEpoch || e <= epoch) revert BadEpoch();
        bytes32 digest = keccak256(abi.encode(address(this), block.chainid, "MIRAGE_FINALIZE", e));
        if (_recover(digest, sig) != oracle) revert BadSignature();
        epoch = e;
        emit EpochFinalized(e);
    }

    // ------------------------------------------------------------------
    // Tallies

    /// @notice yes / no totals in WAD (1e18 = one full vote).
    /// @param weighted false = one account one vote; true = flagged clusters collapse.
    function tally(uint256 id, bool weighted) external view returns (uint256 yes, uint256 no) {
        Proposal storage p = proposals[id];
        yes = uint256(p.yes) * WAD;
        no = uint256(p.no) * WAD;
        if (!weighted || epoch == 0) return (yes, no);
        uint256 e = epoch;
        uint32[] storage ks = _clusters[e];
        for (uint256 i; i < ks.length; ++i) {
            uint32 k = ks[i];
            uint256 size = clusterSize[e][k];
            if (size == 0) continue;
            uint256 y = clusterYes[id][e][k];
            uint256 n = clusterNo[id][e][k];
            if (y + n == 0) continue;
            uint256 w = clusterWeight(size);
            yes = yes - y * WAD + (w * y) / size;
            no = no - n * WAD + (w * n) / size;
        }
    }

    /// @notice total weight of a flagged cluster: 1, or ln(size) (never below 1).
    function clusterWeight(uint256 size) public view returns (uint256) {
        if (mode == Mode.ONE) return WAD;
        uint256 l = lnWad(size);
        return l > WAD ? l : WAD;
    }

    function clustersOf(uint256 e) external view returns (uint32[] memory) {
        return _clusters[e];
    }

    function proposalCount() external view returns (uint256) {
        return proposalIds.length;
    }

    /// @notice natural log of a positive integer, in WAD: binary log2, then * ln 2.
    function lnWad(uint256 n) public pure returns (uint256) {
        require(n >= 1, "ln domain");
        uint256 whole;
        uint256 m = n;
        while (m >= 2) {
            m >>= 1;
            ++whole;
        }
        uint256 r = whole * WAD;
        // normalised mantissa y in [1, 2) (WAD), then one fractional bit per squaring
        uint256 y = (n * WAD) >> whole;
        for (uint256 delta = WAD / 2; delta > 0; delta >>= 1) {
            y = (y * y) / WAD;
            if (y >= 2 * WAD) {
                r += delta;
                y >>= 1;
            }
        }
        return (r * LN2_WAD) / WAD;
    }

    // ------------------------------------------------------------------
    // ECDSA over EIP-191 personal-sign of a 32-byte digest

    function _recover(bytes32 digest, bytes calldata sig) private pure returns (address) {
        if (sig.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (v < 27) v += 27;
        if (uint256(s) > HALF_ORDER) return address(0);
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        return ecrecover(ethHash, v, r, s);
    }
}
