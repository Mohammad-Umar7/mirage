import { expect } from "chai";
import { ethers } from "hardhat";
import type { MirageGovernance } from "../typechain-types";

const coder = ethers.AbiCoder.defaultAbiCoder();
const WAD = 10n ** 18n;
const YES = 1;
const NO = 2;

type Wallet = InstanceType<typeof ethers.Wallet>;

function people(n: number, tag: string): Wallet[] {
  return Array.from({ length: n }, (_, i) => new ethers.Wallet(ethers.keccak256(ethers.toUtf8Bytes(`${tag}-${i}`))));
}

async function deploy(mode = 0) {
  const [owner, oracle, relayer, stranger] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("MirageGovernance");
  const gov = (await factory.deploy(oracle.address, relayer.address, mode)) as unknown as MirageGovernance;
  const { chainId } = await ethers.provider.getNetwork();
  return { gov, owner, oracle, relayer, stranger, chainId, address: await gov.getAddress() };
}

type Ctx = Awaited<ReturnType<typeof deploy>>;

async function signVote(ctx: Ctx, w: Wallet, id: number, choice: number) {
  const digest = ethers.keccak256(
    coder.encode(["address", "uint256", "string", "uint256", "address", "uint8"], [ctx.address, ctx.chainId, "MIRAGE_VOTE", id, w.address, choice]),
  );
  return w.signMessage(ethers.getBytes(digest));
}

async function vote(ctx: Ctx, id: number, voters: Wallet[], choice: number) {
  for (let s = 0; s < voters.length; s += 200) {
    const batch = voters.slice(s, s + 200);
    const sigs = await Promise.all(batch.map((w) => signVote(ctx, w, id, choice)));
    await ctx.gov.connect(ctx.relayer).castVotes(id, batch.map((w) => w.address), batch.map(() => choice), sigs);
  }
}

async function attest(ctx: Ctx, e: number, clusters: { id: number; members: Wallet[] }[]) {
  const ids = clusters.map((c) => c.id);
  const sizes = clusters.map((c) => c.members.length);
  const begin = ethers.keccak256(
    coder.encode(["address", "uint256", "string", "uint256", "uint32[]", "uint32[]"], [ctx.address, ctx.chainId, "MIRAGE_BEGIN", e, ids, sizes]),
  );
  await ctx.gov.beginEpoch(e, ids, sizes, await ctx.oracle.signMessage(ethers.getBytes(begin)));
  const all = clusters.flatMap((c) => c.members.map((m) => ({ addr: m.address, id: c.id })));
  for (let s = 0, chunk = 0; s < all.length; s += 300, chunk++) {
    const part = all.slice(s, s + 300);
    const members = part.map((p) => p.addr);
    const mids = part.map((p) => p.id);
    const digest = ethers.keccak256(
      coder.encode(
        ["address", "uint256", "string", "uint256", "uint256", "address[]", "uint32[]"],
        [ctx.address, ctx.chainId, "MIRAGE_MEMBERS", e, chunk, members, mids],
      ),
    );
    await ctx.gov.attestMembers(e, chunk, members, mids, await ctx.oracle.signMessage(ethers.getBytes(digest)));
  }
  const fin = ethers.keccak256(coder.encode(["address", "uint256", "string", "uint256"], [ctx.address, ctx.chainId, "MIRAGE_FINALIZE", e]));
  await ctx.gov.finalizeEpoch(e, await ctx.oracle.signMessage(ethers.getBytes(fin)));
}

async function setup(mode = 0, swarmSize = 400, honestSize = 100) {
  const ctx = await deploy(mode);
  const swarm = people(swarmSize, "swarm");
  const honest = people(honestSize, "honest");
  const everyone = [...swarm, ...honest].map((w) => w.address);
  for (let s = 0; s < everyone.length; s += 400) await ctx.gov.connect(ctx.relayer).register(everyone.slice(s, s + 400));
  await ctx.gov.connect(ctx.relayer).createProposal(7, "Transfer treasury to 0xa77a…c0de", swarm[0].address, 1_250_000n, 0, 0);
  return { ctx, swarm, honest };
}

describe("MirageGovernance", () => {
  it("naive tally lets a swarm win; weighted tally collapses it to one voice", async () => {
    const { ctx, swarm, honest } = await setup(0);
    await vote(ctx, 7, swarm, YES);
    await vote(ctx, 7, honest, NO);

    const [nYes, nNo] = await ctx.gov.tally(7, false);
    expect(nYes).to.equal(400n * WAD);
    expect(nNo).to.equal(100n * WAD);

    await attest(ctx, 1, [{ id: 42, members: swarm }]);
    const [wYes, wNo] = await ctx.gov.tally(7, true);
    expect(wYes).to.equal(1n * WAD); // 400 accounts, one voice
    expect(wNo).to.equal(100n * WAD);
    expect(wNo > wYes).to.equal(true);
  });

  it("log mode gives a flagged cluster ln(n) votes", async () => {
    const { ctx, swarm, honest } = await setup(1);
    await vote(ctx, 7, swarm, YES);
    await vote(ctx, 7, honest, NO);
    await attest(ctx, 1, [{ id: 7, members: swarm }]);
    const [wYes] = await ctx.gov.tally(7, true);
    const expected = Math.log(400);
    expect(Number(wYes) / 1e18).to.be.closeTo(expected, 1e-6);
  });

  it("counts votes cast after the attestation inside the cluster", async () => {
    const { ctx, swarm, honest } = await setup(0, 200, 50);
    await attest(ctx, 1, [{ id: 3, members: swarm }]);
    await vote(ctx, 7, swarm, YES); // arrives after the epoch is final
    await vote(ctx, 7, honest, NO);
    const [wYes, wNo] = await ctx.gov.tally(7, true);
    expect(wYes).to.equal(1n * WAD);
    expect(wNo).to.equal(50n * WAD);
  });

  it("a newer epoch replaces the old cluster picture", async () => {
    const { ctx, swarm, honest } = await setup(0, 100, 20);
    await vote(ctx, 7, swarm, YES);
    await vote(ctx, 7, honest, NO);
    await attest(ctx, 1, [{ id: 1, members: swarm.slice(0, 50) }]);
    let [wYes] = await ctx.gov.tally(7, true);
    expect(wYes).to.equal(51n * WAD); // 50 unflagged + 1 for the flagged half
    await attest(ctx, 2, [{ id: 1, members: swarm }]);
    [wYes] = await ctx.gov.tally(7, true);
    expect(wYes).to.equal(1n * WAD);
  });

  it("computes natural logs precisely on-chain", async () => {
    const { gov } = await deploy(1);
    for (const n of [1, 2, 3, 10, 400, 1000, 10000]) {
      const got = Number(await gov.lnWad(n)) / 1e18;
      expect(got).to.be.closeTo(Math.log(n), 1e-9);
    }
    expect(await gov.clusterWeight(2)).to.equal(WAD); // never below one person
  });

  it("rejects attestations not signed by the oracle", async () => {
    const { ctx, stranger } = { ...(await setup(0, 10, 5)), stranger: (await ethers.getSigners())[3] };
    const begin = ethers.keccak256(
      coder.encode(["address", "uint256", "string", "uint256", "uint32[]", "uint32[]"], [ctx.address, ctx.chainId, "MIRAGE_BEGIN", 1, [1], [10]]),
    );
    const forged = await stranger.signMessage(ethers.getBytes(begin));
    await expect(ctx.gov.beginEpoch(1, [1], [10], forged)).to.be.revertedWithCustomError(ctx.gov, "BadSignature");
  });

  it("refuses to go back to an older epoch", async () => {
    const { ctx, swarm } = await setup(0, 20, 5);
    await attest(ctx, 2, [{ id: 1, members: swarm }]);
    const begin = ethers.keccak256(
      coder.encode(["address", "uint256", "string", "uint256", "uint32[]", "uint32[]"], [ctx.address, ctx.chainId, "MIRAGE_BEGIN", 1, [1], [20]]),
    );
    await expect(ctx.gov.beginEpoch(1, [1], [20], await ctx.oracle.signMessage(ethers.getBytes(begin)))).to.be.revertedWithCustomError(
      ctx.gov,
      "BadEpoch",
    );
  });

  it("skips forged, duplicate and unregistered votes without failing the batch", async () => {
    const { ctx, honest } = await setup(0, 5, 5);
    const outsider = people(1, "outsider")[0];
    const forgedSig = await signVote(ctx, honest[1], 7, YES); // signed by someone else
    const good = await signVote(ctx, honest[0], 7, YES);
    const unreg = await signVote(ctx, outsider, 7, YES);
    await ctx.gov
      .connect(ctx.relayer)
      .castVotes(7, [honest[0].address, honest[2].address, outsider.address], [YES, YES, YES], [good, forgedSig, unreg]);
    await ctx.gov.connect(ctx.relayer).castVotes(7, [honest[0].address], [NO], [await signVote(ctx, honest[0], 7, NO)]);
    const [yes, no] = await ctx.gov.tally(7, false);
    expect(yes).to.equal(1n * WAD);
    expect(no).to.equal(0n);
  });

  it("only the relayer registers and relays; only the owner changes mode", async () => {
    const { ctx } = await setup(0, 5, 5);
    await expect(ctx.gov.connect(ctx.stranger).register([ctx.stranger.address])).to.be.revertedWithCustomError(ctx.gov, "NotRelayer");
    await expect(ctx.gov.connect(ctx.stranger).setMode(1)).to.be.revertedWithCustomError(ctx.gov, "NotOwner");
    await ctx.gov.connect(ctx.owner).setMode(1);
    expect(await ctx.gov.mode()).to.equal(1n);
  });
});
