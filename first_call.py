import sys

from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError

MODEL = "gpt-5.4-mini"
# USD per 1M tokens, from OpenAI's pricing page (checked 2026-10-02)
PRICE_IN = 0.75
PRICE_OUT = 4.50

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from the environment by itself

question = "რა არის ხელოვნური ინტელექტი? უპასუხე ორ წინადადებაში."

try:
    response = client.responses.create(
        model=MODEL,
        instructions="You are a helpful assistant. Always answer in Georgian.",
        input=question,
    )
except AuthenticationError:
    sys.exit("Error: the API key was rejected. Check OPENAI_API_KEY in .env.")
except RateLimitError as e:
    sys.exit(f"Error: rate limit hit or no credit left ({e.code}). Check billing.")
except APIConnectionError:
    sys.exit("Error: couldn't reach OpenAI. Check your internet connection.")

usage = response.usage
cost = usage.input_tokens / 1_000_000 * PRICE_IN + usage.output_tokens / 1_000_000 * PRICE_OUT

print(response.output_text)
print(f"\ntokens: {usage.input_tokens} in, {usage.output_tokens} out")
print(f"cost: ${cost:.6f}")