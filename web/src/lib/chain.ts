"use client";

import { useEffect, useState } from "react";
import { createPublicClient, http, parseAbi, type PublicClient } from "viem";
import type { Tally } from "./protocol";
import { useMirage } from "./store";

const ABI = parseAbi([
  "function tally(uint256 id, bool weighted) view returns (uint256 yes, uint256 no)",
  "function epoch() view returns (uint256)",
  "function mode() view returns (uint8)",
  "function registeredCount() view returns (uint256)",
]);

const WAD = BigInt("1000000000000000000");
const MILLI = BigInt(1000);
const toVotes = (x: bigint) => Number((x * MILLI) / WAD) / 1000;

let client: PublicClient | null = null;
let clientRpc = "";

function getClient(rpc: string): PublicClient {
  if (!client || clientRpc !== rpc) {
    client = createPublicClient({ transport: http(rpc) });
    clientRpc = rpc;
  }
  return client;
}

export type OnchainRead = {
  naive: Tally;
  weighted: Tally;
  epoch: number;
  block: number;
  registered: number;
  at: number;
};

/** Reads both tallies for a proposal straight from the contract with viem. */
export function useOnchainTally(pid: number | null, active: boolean): OnchainRead | null {
  const chain = useMirage((s) => s.chain);
  const [read, setRead] = useState<OnchainRead | null>(null);
  const address = chain?.address as `0x${string}` | undefined;
  const rpc = chain?.rpc;
  const world = (chain as unknown as { world?: number } | null)?.world ?? 0;
  const connected = !!chain?.connected;

  useEffect(() => {
    if (!active || pid === null || !address || !rpc || !connected) return;
    let stop = false;
    const c = getClient(rpc);
    const id = BigInt(world * 1000 + pid);
    const poll = async () => {
      try {
        const [[ny, nn], [wy, wn], epoch, block, registered] = await Promise.all([
          c.readContract({ address, abi: ABI, functionName: "tally", args: [id, false] }),
          c.readContract({ address, abi: ABI, functionName: "tally", args: [id, true] }),
          c.readContract({ address, abi: ABI, functionName: "epoch" }),
          c.getBlockNumber(),
          c.readContract({ address, abi: ABI, functionName: "registeredCount" }),
        ]);
        if (!stop) {
          setRead({
            naive: { yes: toVotes(ny), no: toVotes(nn) },
            weighted: { yes: toVotes(wy), no: toVotes(wn) },
            epoch: Number(epoch),
            block: Number(block),
            registered: Number(registered),
            at: Date.now(),
          });
        }
      } catch {
        /* chain offline: the view falls back to the backend's off-chain tally */
      }
    };
    poll();
    const t = setInterval(poll, 2000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [active, pid, address, rpc, world, connected]);

  return read;
}
