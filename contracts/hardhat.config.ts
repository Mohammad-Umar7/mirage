import "@nomicfoundation/hardhat-toolbox";
import type { HardhatUserConfig } from "hardhat/config";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true },
  },
  networks: {
    hardhat: {
      chainId: 31337,
      // oracle attestations write hundreds of cluster assignments per tx
      blockGasLimit: 60_000_000,
      allowUnlimitedContractSize: false,
    },
    localhost: { url: "http://127.0.0.1:8545", chainId: 31337 },
  },
  mocha: { timeout: 120_000 },
};

export default config;
