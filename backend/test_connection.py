"""Quick smoke test for Supabase + Anthropic + OpenAI connectivity."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def check(name: str, fn) -> bool:
    print(f"  {name:.<45}", end=" ", flush=True)
    try:
        fn()
        print("OK")
        return True
    except Exception as exc:
        print(f"FAIL\n    {type(exc).__name__}: {exc}")
        return False


def supabase_db():
    from services.supabase_client import get_supabase

    sb = get_supabase()
    res = sb.table("recordings").select("id").limit(1).execute()
    assert res.data is not None, "no data returned"


def supabase_storage():
    from services.supabase_client import get_storage_bucket, get_supabase

    sb = get_supabase()
    bucket = get_storage_bucket()
    files = sb.storage.from_(bucket).list()
    assert isinstance(files, list)


def supabase_jwks():
    from services.auth import _jwks_client

    keys = _jwks_client().get_signing_keys()
    assert len(keys) >= 1, "no JWKS keys"


def openai_models():
    from openai import OpenAI

    OpenAI(api_key=os.environ["OPENAI_API_KEY"]).models.list()


def anthropic_models():
    from anthropic import Anthropic

    Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).models.list()


def main():
    print("\n=== PSY backend connectivity check ===\n")
    results = [
        check("Supabase DB (select from recordings)", supabase_db),
        check("Supabase Storage (list bucket)", supabase_storage),
        check("Supabase Auth JWKS (fetch keys)", supabase_jwks),
        check("OpenAI API (list models)", openai_models),
        check("Anthropic API (list models)", anthropic_models),
    ]
    print()
    if all(results):
        print("All checks passed.")
        sys.exit(0)
    print(f"{results.count(False)}/{len(results)} checks failed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
