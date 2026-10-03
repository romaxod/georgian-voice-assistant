"""Step 1.2: terminal chat with memory for ჯიხვი (Jikhvi), a fictional Georgian mobile operator.

Run:  python chat.py              type questions; empty input, "exit" or Ctrl-D quits; "/reset" forgets
      python chat.py --no-memory  break test: every turn is sent alone, so follow-ups lose their context
"""
import argparse
import sys

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

MODEL = "gpt-5.4-mini"
# USD per 1M tokens, from OpenAI's pricing page (checked 2026-10-02)
PRICE_IN = 0.75
PRICE_OUT = 4.50

# The facts live in the prompt for now; step 1.3 moves them into SQLite behind lookup_faq().
SYSTEM_PROMPT = """You are the customer service assistant of ჯიხვი (Jikhvi), a fictional Georgian mobile operator.
Always answer in Georgian, in 1-3 short sentences: your answers will later be read aloud.
Answer only from the facts below. If the answer isn't there, say you don't know and offer to connect the customer to a human operator.
You can't perform actions (blocking a SIM, changing a plan, payments). Never claim you did; tell the customer how to do it.

Facts:
- ტარიფები (monthly plans): „ჯიხვი S" 15 ₾ (10 GB, 300 წუთი); „ჯიხვი M" 25 ₾ (30 GB, ულიმიტო ზარები ქსელში); „ჯიხვი L" 40 ₾ (ულიმიტო ინტერნეტი და ზარები).
- ტარიფის შეცვლა: აპლიკაციაში, „ჩემი ტარიფი" → „შეცვლა". უფასოა, მოქმედებს მომდევნო თვიდან.
- როუმინგი: ევროპის პაკეტი 20 ₾ (7 დღე, 3 GB), ჩაირთვება აპლიკაციიდან. პაკეტის გარეშე 1 MB 1 ₾ ღირს.
- eSIM: აქტივაცია უფასოა, აპლიკაციაში QR კოდით. ფიზიკური SIM ბარათის შეცვლა 5 ₾ ღირს ნებისმიერ ფილიალში.
- SIM ბარათის დაკარგვა: დაბლოკეთ აპლიკაციაში „უსაფრთხოება" → „SIM-ის დაბლოკვა", ან მიმართეთ ფილიალს პირადობით.
- ბალანსის შევსება: აპლიკაციით, ბარათით ან სწრაფი გადახდის აპარატით. საკომისიო 0 ₾.
- ფილიალები: ორშაბათი-შაბათი 10:00-19:00. აპლიკაციის ჩატი მუშაობს 24/7."""


def cost(usage) -> float:
    return usage.input_tokens / 1_000_000 * PRICE_IN + usage.output_tokens / 1_000_000 * PRICE_OUT


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal chat with the ჯიხვი assistant.")
    parser.add_argument("--no-memory", action="store_true", help="send only the latest message (break test)")
    args = parser.parse_args()

    load_dotenv()
    client = OpenAI()  # reads OPENAI_API_KEY from the environment by itself
    history: list[dict] = []  # every user and assistant message so far; resent on every call
    total_cost = 0.0

    print('ჯიხვი assistant. Ask in Georgian. "/reset" forgets the conversation, "exit" or Ctrl-D quits.')
    while True:
        try:
            question = input("\nთქვენ: ").strip()
        except (EOFError, KeyboardInterrupt):  # Ctrl-D, Ctrl-C, or the end of piped input
            break
        if question.lower() in ("", "exit", "quit"):
            break
        if question == "/reset":
            history.clear()
            print("(history cleared)")
            continue

        history.append({"role": "user", "content": question})
        # The model is stateless: it only knows what we send in this call.
        messages = history if not args.no_memory else history[-1:]
        sent = len(messages)
        try:
            response = client.responses.create(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                input=messages,
                store=False,  # we keep the history ourselves; no reason to have OpenAI store it
            )
        except AuthenticationError:
            sys.exit("Error: the API key was rejected. Check OPENAI_API_KEY in .env.")
        except (RateLimitError, APIConnectionError, APIStatusError) as e:
            history.pop()  # drop the unanswered question so history stays user/assistant pairs
            print(f"Error: {type(e).__name__}: {getattr(e, 'message', e)}. Try again or type exit.")
            continue

        answer = response.output_text
        history.append({"role": "assistant", "content": answer})
        turn_cost = cost(response.usage)
        total_cost += turn_cost
        print(f"ჯიხვი: {answer}")
        print(f"  [{response.usage.input_tokens} in / {response.usage.output_tokens} out tokens, "
              f"${turn_cost:.5f}; session ${total_cost:.5f}; {sent} messages sent]")


if __name__ == "__main__":
    main()
