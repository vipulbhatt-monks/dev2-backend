import os
import httpx
from supabase import create_client, Client


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    client = create_client(url, key)

    # Fix SSL on Windows — remove this before deploying to production
    if os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true":
        no_ssl_transport = httpx.HTTPTransport(verify=False)
        client.postgrest.session._transport = no_ssl_transport

    return client


# single shared instance used across the entire app
supabase = get_supabase_client()