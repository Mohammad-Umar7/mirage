// Deploys MirageGovernance to the local chain and writes deployments/local.json
// (address + ABI) for the backend oracle/relayer and the frontend.
import { mkdirSync, writeFileSync } from "fs";
import path from "path";
import { artifacts, ethers } from "hardhat";

async function main() {
  const [relayer, oracle] = await ethers.getSigners();
  const mode = process.env.MIRAGE_WEIGHT_MODE === "log" ? 1 : 0;
  const factory = await ethers.getContractFactory("MirageGovernance");
  const gov = await factory.deploy(oracle.address, relayer.address, mode);
  await gov.waitForDeployment();
  const address = await gov.getAddress();
  const artifact = await artifacts.readArtifact("MirageGovernance");
  const { chainId } = await ethers.provider.getNetwork();
  const out = {
    address,
    chainId: Number(chainId),
    rpc: process.env.MIRAGE_RPC ?? "http://127.0.0.1:8545",
    relayer: relayer.address,
    oracle: oracle.address,
    mode: mode ? "log" : "one",
    deployTx: gov.deploymentTransaction()?.hash ?? null,
    deployedAt: new Date().toISOString(),
    abi: artifact.abi,
  };
  const dir = path.resolve(__dirname, "../../deployments");
  mkdirSync(dir, { recursive: true });
  writeFileSync(path.join(dir, "local.json"), JSON.stringify(out, null, 2));
  console.log(`MirageGovernance deployed at ${address} (chain ${out.chainId}, mode ${out.mode})`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
