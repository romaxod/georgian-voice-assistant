import os
from dotenv import load_dotenv

load_dotenv()  # reads .env and puts its lines into environment variables

for name in ["OPENAI_API_KEY", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]:
    value = os.getenv(name)
    if value:
        print(f"{name}: key loaded ({len(value)} chars)")
    else:
        print(f"{name}: MISSING")