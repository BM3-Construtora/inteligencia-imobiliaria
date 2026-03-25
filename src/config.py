import os
from dotenv import load_dotenv

load_dotenv()


# Supabase (nosso projeto)
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# Toca Imóveis
TOCA_SUPABASE_URL = os.getenv(
    "TOCA_SUPABASE_URL", "https://jveljofutivtmufzmiej.supabase.co"
)
TOCA_ANON_KEY = os.getenv(
    "TOCA_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2ZWxqb2Z1dGl2dG11ZnptaWVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY3NDA0NzYsImV4cCI6MjA3MjMxNjQ3Nn0.Jl4X9G3Uy-4FrBRiQdVZ7Zvv0tHsg4VEq1mou1yofK0",
)

# União / DreamKeys
UNIAO_API_URL = os.getenv(
    "UNIAO_API_URL", "https://api.dreamkeys.com.br/public/properties"
)

# Config
MAX_PAGES_PER_SPIDER = int(os.getenv("MAX_PAGES_PER_SPIDER", "20"))
