# Python Environment Setup for Qlib

This document outlines the steps taken to set up the quantitative layer of the Dexter Quant Agent.

## Steps Performed

1.  **Virtual Environment Creation**
    *   Path: `c:\Users\jmgra\antigravityagents\dexter-quant-agent\quant-env`
    *   Command: `python -m venv quant-env`

2.  **Qlib Installation**
    *   Command: `.\quant-env\Scripts\python.exe -m pip install git+https://github.com/microsoft/qlib.git`
    *   *Note: Due to Python 3.14 being the primary system version, Qlib is being installed directly from source to ensure compatibility and dependency resolution.*

3.  **Dependency Check: Microsoft C++ Build Tools**
    *   Status: **Verified**. Found in `C:\Program Files (x86)\Microsoft Visual Studio\2022`.
    *   *Note: These tools are required for compiling LightGBM and other C++ extensions used by Qlib.*

4.  **Verification Script**
    *   Script: `test_qlib.py`
    *   Command: `.\quant-env\Scripts\python.exe test_qlib.py`

## Troubleshooting

If `test_qlib.py` fails, ensure that:
- You have a stable internet connection for dependency downloads.
- Visual Studio Build Tools are correctly installed with the "Desktop development with C++" workload.
- No other Python processes are locking the `quant-env` directory.
