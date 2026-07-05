import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.sandbox import run_python_in_sandbox


def _has_e2b_api_key() -> bool:
    api_key = (os.getenv("E2B_API_KEY") or "").strip()
    return bool(api_key and api_key not in {",", "your_e2b_api_key"})


def main() -> None:
    load_dotenv()

    if not _has_e2b_api_key():
        print("E2B_API_KEY is not set. Add it to .env to run the real sandbox test.")
        return

    result = run_python_in_sandbox('print("hello from sandbox")')

    print(f"status: {result['status']}")
    print(f"stdout: {result['stdout']}")
    print(f"stderr: {result['stderr']}")
    print(f"error: {result['error']}")


if __name__ == "__main__":
    main()
