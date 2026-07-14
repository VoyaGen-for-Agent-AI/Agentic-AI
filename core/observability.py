import os
from typing import Any


def get_langfuse_callbacks() -> list[Any]:
    """Return Langfuse callbacks when credentials are configured."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"

    if not public_key or not secret_key:
        return []

    os.environ.setdefault("LANGFUSE_HOST", host)

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        print("Langfuse is not installed; continuing without tracing.")
        return []

    try:
        return [CallbackHandler()]
    except Exception as exc:
        print(f"Langfuse callback disabled: {exc}")
        return []
