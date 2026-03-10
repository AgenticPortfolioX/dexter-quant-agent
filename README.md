> 🕒 Last Updated: 03-09-2026 11:15 PM EST

# Dexter Quant Agent

An autonomous financial research and quantitative trading agent that combines the reasoning capabilities of [Dexter](https://github.com/virattt/dexter) with the AI-powered quant engine [Qlib](https://github.com/microsoft/qlib).

## 🏗️ Architecture

1.  **Orchestration Layer (Dexter Core)**: Bun/TypeScript environment running the reasoning loop.
2.  **Quant Layer (Qlib Bridge)**: Python 3.14 environment with Qlib installed for factor mining and backtesting.
3.  **User Strategy Layer**: Storage and ingestion for user-provided alpha signals.

## 🚀 Quick Start (Windows)

### Prerequisites
- **Bun**: `powershell -c "irm bun.sh/install.ps1 | iex"`
- **Python 3.8+**: (Installed and verified on 3.14.2)
- **Microsoft C++ Build Tools**: Required for Qlib extensions.

### Installation
1.  **Clone Core**: `git clone https://github.com/virattt/dexter.git dexter-core`
2.  **Install Node Deps**: `cd dexter-core && bun install`
3.  **Setup Python**: 
    ```bash
    python -m venv quant-env
    .\quant-env\Scripts\python.exe -m pip install git+https://github.com/microsoft/qlib.git
    ```

### Running the Agent
1.  **Add API Keys**: Copy `dexter-core/env.example` to `dexter-core/.env` and add your keys (OpenAI, Financial Datasets, Exa).
2.  **Start Server**: Run `start.bat` from the root or `bun run start:server` inside `dexter-core`.

## 🧠 Advanced Capabilities (The Orchestrator Upgrades)

Dexter has been upgraded from a standard quant bot to a **Financial Super-Agent** with the following "Hard Logic" modules:

### 1. **Active Surveillance Mode**
Dexter operates in a persistent monitoring loop. This is not passive; he actively polls:
*   **Venue Arbitrage**: Tracking Delta between Robinhood Prediction Markets and Polymarket.
*   **Threshold Scanning**: Monitoring for "Red Opportunity" entries (e.g., HOOD < $78, LINK < $8.30).
*   **Indicator Convergence**: Triggering only when RSI < 30 aligns with Support Floor Bids.

### 2. **Derivatives & LEAPS Strategist (Skill 12)**
*   **Greeks Audit**: Calculation of Delta-adjusted exposure and Theta "rent" per day.
*   **IV Skew Analysis**: Identifying if options are overpriced relative to historical volatility.
*   **LEAPS Efficiency**: Modeling 2-year recovery plays for maximum capital leverage.

### 3. **On-Chain Liquidity Physicist (Skill 13)**
*   **Infrastructure Audit**: Real-time tracking of Chainlink CCIP volume and fee generation.
*   **Supply Shock Dynamics**: Monitoring Staking v0.2 utilization and exchange outflows.
*   **Programmable Solvency**: Auditing Proof of Reserve (PoR) "Secure Mint" health to find structural floor value.

### 4. **Whale & Smart-Money Shadow Tracker (Skill 14)**
*   **Dark Pool Forensics**: Identifying institutional block trades hidden from the public tape.
*   **Exhaustion Signal**: Tracking when retail sentiment is at record lows while whale accumulation is at record highs.
*   **Insider Signal**: Cross-referencing SEC Form 4 filings with immediate price action.

### 5. **Structural Value Moat Analyzer (Skill 11)**
*   **Hard Logic Extraction**: Bypassing headlines to evaluate economic flywheels and technical moats.
*   **Solvency Enforcement**: Prioritizing assets where security is enforced by the Risk Management Network (RMN).

## 🚀 Live Strategies
*   **SMC Focal Portfolio**: Smart Money Concept strategy (Breakers, FVG, Liquidity Grabs) currently live on Robinhood.
*   **Gemini Velocity**: Momentum Flow model (ADX + StochRSI) focused on high-performance runners (**HOOD, COIN, TSM, ROKU**).
*   **Structural LEAPS Play**: Multi-year accumulation plan for HOOD & LINK based on infra-level moats.

## 🧪 Active Testing
*   **Volcanix (VWAP Reclaim)**: VWAP Rejection and Reclaim model with Volume confirmation. Active on liquid Dow and Nasdaq components.
*   **Nova (Optimized)**: Volatility Squeeze Breakout with Macro Alignment. Filtered for high-probability assets (**MSTR, AAPL, AMZN, TSM, NVDA, QCOM, PLTR**) with >50% backtest win rates.

## 🔌 API Reference

### POST `/query`
Send a natural language query to the agent.
- **Payload**: `{ "query": "Build a momentum strategy for tech stocks." }`
- **Response**: `{ "answer": "..." }`

## 🛠️ Tools
- `qlib_factor_mining`: Identify driving factors.
- `qlib_train_model`: Train predictive models.
- `qlib_backtest`: Evaluation performance.
- `ingest_strategy`: Add your own JSON/Python strategies.
- `deploy_strategy`: Paper trade in a simulator.

## 📁 Folder Structure
- `dexter-core/`: Main agent logic and HTTP server.
- `quant-env/`: Python virtual environment.
- `quant_scripts/`: Python logic for Qlib operations.
- `user_strategies/`: Storage for user-defined strategies.
- `test-request.js`: Simple script to test the HTTP API.
