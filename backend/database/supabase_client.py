from supabase import create_client

from config import settings

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client
