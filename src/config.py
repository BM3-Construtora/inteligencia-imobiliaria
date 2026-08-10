import os
from dotenv import load_dotenv

load_dotenv()


# Supabase (nosso projeto)
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# Toca Imóveis — credenciais de terceiro. Nunca versionar a anon key aqui:
# defina TOCA_SUPABASE_URL e TOCA_ANON_KEY no .env / GitHub Secrets. Vazio =
# coletor Toca falha com mensagem clara (ver src/collectors/toca.py), sem
# derrubar o resto do pipeline no import.
TOCA_SUPABASE_URL = os.getenv("TOCA_SUPABASE_URL", "").strip()
TOCA_ANON_KEY = os.getenv("TOCA_ANON_KEY", "").strip()

# União / DreamKeys
UNIAO_API_URL = (
    os.getenv("UNIAO_API_URL") or "https://api.dreamkeys.com.br/public/properties"
)

# Config
MAX_PAGES_PER_SPIDER = int(os.getenv("MAX_PAGES_PER_SPIDER", "20"))

# Multi-city — vazio = usa todas as cidades ativas em `cities` table
CITY_FOCUS = os.getenv("CITY_FOCUS", "").strip()

# Computer Vision
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")
