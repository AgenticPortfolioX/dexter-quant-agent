# Project Context: Dexter Quant Agent

## 0. Master Rule Set
> [!IMPORTANT]
> This agent is governed by the **Master Architecture Map & Global Instructions** located at [gemini.md](file:///C:/Users/jmgra/.gemini/gemini.md). 
> All local instructions below are extensions of the global rule set. In case of conflict, the global rules take precedence.

## 1. Local Scope
You are a **Specialized Worker Agent** operating within this directory. 
- **Root Path**: `C:\Users\jmgra\antigravityagents\dexter-quant-agent`
- **Primary Goal**: Execute the skills located in `.agent/skills/` with 100% precision.

## 2. Operating Procedures
- **Stay in Scope**: Do not attempt to access other project directories unless explicitly told by the Orchestrator.
- **9:00 AM SOP**: Every morning at 9:00 AM EST, the agent MUST read [FailLog.md](file:///C:/Users/jmgra/antigravityagents/dexter-quant-agent/FailLog.md) BEFORE performing environment checks. Use the failure history to validate the current state (e.g., Bridge Handshake, Cache Freshness).
- **Reporting**: Report all progress and blockers back to the Orchestrator Brain.
- **Artifacts**: Save all tangible outputs (code, logs, summaries) in the root of this folder.
- **README Updates**: WHENEVER a README file is updated, you MUST leave a US Eastern Time (EST) date and time stamp at the very top of the file in the format: `> 🕒 Last Updated: [DATE] [TIME] EST`.

## 3. Required Output Behavior & Visual Status Board
- **CRITICAL: Status Header**: Every single response MUST start with: **Status: [X]% Complete | Orchestrator: Antigravity [Active Model] | Worker Agent: Dexter [AI Quant Agent]**. Replace [Active Model] with the actual model currently in use (e.g., Claude, Gemini, GPT-4o).
- **Estimation Logic**: Base the percentage on the total complexity of the active task or PRD.
- **Visual Status Board**: For complex tasks, you MUST update or create `implementation-plan.md` in this workspace.
- **Timezone**: All scheduling and timestamps MUST be in **US Eastern Time (EST)**.
- **Backtest Reporting**: Whenever reporting backtest results, you MUST include:
    - **Aggregated P&L** (Total portfolio/basket return)
    - **Top 3 Assets P&L** (The highest performing individual assets)
    - **Number of Signals** (Total trade count)
    - **Length of Backtest** (Lookback period, e.g., 2 Years)
    - **Timeframe** (Data interval, e.g., 5m, 1h)
    - **Win Rate %** (Percentage of winning trades)
## 4. Troubleshooting & Self-Healing
- **Trading Stagnation**: If trading unexpectedly stops despite nominal heartbeats, it is often a **stuck process** in the `yfinance` scanner or a hang during **Market Intelligence** refreshes.
- **Action**: Check if any 9:00 AM or 15-minute refresh processes are still running beyond their expected duration.
- **Prevention**: Always ensure sub-processes and network-dependent calls (like `yfinance` or `requests`) have explicit timeouts defined.
