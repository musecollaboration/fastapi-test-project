import os
from dotenv import load_dotenv
from pathlib import Path
from pydantic_settings import BaseSettings

if not os.getenv("DATABASE_URL"):
    load_dotenv(Path(__file__).parent / ".env")


class Settings(BaseSettings):
    DATABASE_URL: str


settings = Settings()  # type: ignore
