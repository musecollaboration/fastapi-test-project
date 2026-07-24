from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).parent / ".env")


class Settings(BaseSettings):
    DATABASE_URL: str


settings = Settings() # type: ignore
