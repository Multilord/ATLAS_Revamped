"""Server-only environment configuration."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = field(default_factory=lambda: os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017'), repr=False)
    database: str = field(default_factory=lambda: os.getenv('MONGODB_DATABASE', 'atlas_solution_engine'))
    mongo_timeout: int = field(default_factory=lambda: int(os.getenv('MONGODB_TIMEOUT_MS', '5000')))
    api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', '').strip(), repr=False)
    model: str = field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))
    embedding_model: str = field(default_factory=lambda: os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'))
    ai_timeout: int = field(default_factory=lambda: int(os.getenv('OPENAI_TIMEOUT_SECONDS', '90')))
    customer: str = field(default_factory=lambda: os.getenv('WORKSPACE_CUSTOMER', 'My Workspace').strip())
    consultant: str = field(default_factory=lambda: os.getenv('CONSULTANT_NAME', 'Consultant').strip())
    port: int = field(default_factory=lambda: int(os.getenv('PORT', '8000')))


settings = Settings()
