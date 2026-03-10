# Dexter Momentum Ensemble: The Dual-Layer Orchestrator

## 🎯 Goal
To maximize capital efficiency by only executing "Narrative" signals that survive the "Structural" quality filter. This ensemble prevents Dexter from being lured into "Value Traps" or high-hype/low-quality rotations.

## 🏗️ The Hierarchy of Execution

### Layer 1: The Narrative Signal (The "Scouts")
Dexter runs three distinct "narrative" scanners throughout the day/month:
1.  **Post-Earnings Drift (S1)**: Checks for fundamental surprises and raised guidance.
2.  **Sector Rotation (S2)**: Identifies monthly institutional flows into the strongest ETFs.
3.  **Follow the Leader (S4)**: Tracks significant, discretionary open-market insider buys.

### Layer 2: The Quality Gatekeeper (The "Truth")
Before a cent is committed, any asset identified in Layer 1 MUST pass:
*   **Strategy 3 (Value Trap Filter)**:
    *   **Interest Coverage > 3.0** (Can they pay their bills?)
    *   **FCF Yield > 5%** (Are they actually making cash?)
    *   **Altman Z-Score > 1.8** (Are they going bankrupt?)
    *   **PE < 5-Yr Median** (Is the value proposition historically valid?)

---

## 🚦 Scoring & Position Sizing Rules

| Signal Composition | Quality Filter (S3) | Dexter's Command | Size (Portfolio %) |
| :--- | :--- | :--- | :--- |
| Any Signal (S1, S2, or S4) | **FAIL** | **HARD REJECT** | 0% |
| **Sector Rotation** (S2) | **PASS** | Standard Entry | 2.5% |
| **Insider Buy** (S4) | **PASS** | Standard Entry | 2.0% |
| **Earnings Catalyst** (S1) | **PASS** | Standard Entry | 3.0% |
| **Stacked Narrative** (S1 + S4) | **PASS** | **POWER MOVE** | 6.0% |
| **Stacked Narrative** (S1 + S4 + S2) | **PASS** | **ULTIMATE CONVICTION**| 8.0% |

---

## 🛠️ Operational Workflow

1.  **Scan Phase (09:30 - 10:30 EST)**:
    *   Run `Post-Earnings` and `Follow the Leader` strategy scripts.
    *   Queue all potential candidates in a `PENDING_SCAN` list.

2.  **Filter Phase (Instant)**:
    *   Pass every `PENDING_SCAN` ticker through the `ValueTrapFilter`.
    *   Log all rejects in `value_trap_rejects.log` for future post-mortems (helps refine the filter).

3.  **Execution (11:00 EST)**:
    *   Any candidate that survives the Filter Phase is checked for **Overlap** (Multiple signals for one ticker).
    *   Calculate final weight using the **Scoring Table** above.
    *   Execute via Robinhood Bridge.

4.  **Monthly Cycle**:
    *   On the 1st of every month, `Sector Rotation` signals are generated and passed through the Gatekeeper to refresh the macro portfolio.

---

## 📢 Orchestrator Notation
By coupling the **Growth/Momentum** of S1 and S4 with the **Statistical Quality** of S3, Dexter effectively operates like a "Quality-Factor" fund. He captures the upside of a breakout while the Gatekeeper protects him from the downside of a fundamental collapse.
