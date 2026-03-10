# Agent Hierarchy & Data Flow

```mermaid
graph TD
    %% Levels
    User((User Prompt)) --> Orchestrator[Orchestrator Brain]

    subgraph Specialist_Agents [Specialist Agent Layer]
        Orchestrator --> DeepSeek[Coding Agent: DeepSeek V3.2]
        Orchestrator --> MarketResearch[Market Researcher]
        Orchestrator --> DexterQuant[Dexter Quant Agent]
    end

    %% Market Researcher Skills
    subgraph Fundamental_Skills [10 Research Skills]
        MarketResearch --> S1[DCF Valuation]
        MarketResearch --> S2[Relative Valuation]
        MarketResearch --> S3[Earnings Analysis]
        MarketResearch --> S4[Sentiment Analysis]
        MarketResearch --> S5[Risk Assessment]
        MarketResearch --> S6[Industry Benchmarking]
        MarketResearch --> S7[Dividend Analysis]
        MarketResearch --> S8[Insider Activity]
        MarketResearch --> S9[Macro Outlook]
        MarketResearch --> S10[Technical Indicators]
    end

    %% Dexter Quant Capabilities
    subgraph Quant_Logic [Quant Engine]
        DexterQuant --> Q1[Factor Mining]
        DexterQuant --> Q2[Model Training]
        DexterQuant --> Q3[Backtesting]
        DexterQuant --> Q4[User Strategy Ingestion]
    end

    %% Data Flow Back Up
    DeepSeek --> |Optimized Code| Orchestrator
    Fundamental_Skills --> |Fundamental Data| MarketResearch
    MarketResearch --> |Research Insights| Orchestrator
    Quant_Logic --> |Quant Metrics| DexterQuant
    DexterQuant --> |Strategy Performance| Orchestrator

    %% Final Output
    Orchestrator --> Report[Master Artifact / Final Report]
    Report --> User
```

### Data Flow Overview:
1. **Initiation**: User sends a complex financial/coding request to the **Orchestrator**.
2. **Delegation**: The Orchestrator analyzes the intent and delegates tasks:
    - **DeepSeek (Coder)**: Handles algorithm optimization and script generation.
    - **Market Researcher**: Triggers 10 specialized fundamental skills (e.g., DCF, Sentiment) to gather ground-truth data.
    - **Dexter Quant**: Manages factor mining and backtesting via Qlib to validate quantitative hypotheses.
3. **Synthesis**: Specialist agents return their specific outputs (data points, code blocks, backtest results).
4. **Conclusion**: The Orchestrator compiles these into a structured **Master Artifact** delivering a comprehensive final report to the User.
