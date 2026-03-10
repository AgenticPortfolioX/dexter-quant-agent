import sys
try:
    import qlib
    print("Qlib installed successfully")
    print(f"Qlib version: {qlib.__version__}")
except ImportError:
    print("Qlib is NOT installed")
    sys.exit(1)
except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)
