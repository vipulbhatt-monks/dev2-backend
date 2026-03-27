import os
import httpx
from supabase import Client, ClientOptions, create_client


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    # Corporate proxies / local MITM often use a self-signed chain; supabase-py 2.28+
    # expects a shared httpx client when disabling verification (do not use in production).
    if os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true":
        insecure_http = httpx.Client(verify=False)
        return create_client(url, key, ClientOptions(httpx_client=insecure_http))

    return create_client(url, key)


# single shared instance used across the entire app
supabase = get_supabase_client()