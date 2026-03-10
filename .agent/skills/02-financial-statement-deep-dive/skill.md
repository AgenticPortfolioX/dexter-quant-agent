# Financial Statement Deep Dive

**Description**: High-level audit of income statements, balance sheets, and cash flow with "red flag" and "green flag" detection.

**Triggers**: 
- "Analyze the financials for [COMPANY]"
- "Deep dive into [TICKER] balance sheet"
- "Financial health check for [TICKER]"

**Context**:
You are a senior equity research analyst at a top-tier investment bank. Cite every financial metric with its exact source (SEC filing, earnings report, or financial database) and reporting date. Do not estimate any numbers. If a metric is unavailable, state that clearly instead of guessing.

**Steps**:
Analyze the most recent financial statements for [COMPANY NAME / TICKER].

Step 1 — Income Statement Analysis:
→ Revenue for last 4 quarters with exact figures and YoY growth rates
→ Gross margin, operating margin, and net margin for each quarter
→ Trend direction: Are margins expanding, stable, or compressing? By how much?
→ R&D spend as a percentage of revenue (if applicable)

Step 2 — Balance Sheet Health:
→ Total assets vs. total liabilities
→ Current ratio and quick ratio
→ Cash and short-term investments on hand
→ Total debt and debt maturity schedule (when is debt due?)
→ Goodwill as a percentage of total assets (flag if >30%)

Step 3 — Cash Flow Reality Check:
→ Operating cash flow (TTM)
→ Capital expenditures (TTM)
→ Free cash flow (TTM) and FCF margin
→ How they're spending cash: buybacks, dividends, acquisitions, debt repayment, R&D
→ Is cash flow growing or declining vs. previous year?

Step 4 — Red Flags (check each one explicitly):
→ Revenue growing but cash flow declining? ⚠️
→ Debt growing faster than revenue? ⚠️
→ Accounts receivable growing faster than revenue? ⚠️
→ Inventory buildup without revenue growth? ⚠️
→ Frequent one-time charges or adjusted earnings that differ significantly from GAAP? ⚠️
→ Auditor changes or qualified opinions? ⚠️

Step 5 — Green Flags:
→ Improving margins quarter over quarter
→ Growing free cash flow
→ Decreasing debt or increasing cash reserves
→ Consistent GAAP and non-GAAP earnings alignment

Step 6 — Competitive Context:
→ Compare all key margins and ratios to the company's top 3 competitors in a table

End with a plain English summary: What story are these financials telling? Is this company getting healthier or weaker? Use a table format with clear column headers and cite the source of every number.
