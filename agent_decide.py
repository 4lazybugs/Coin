import json
from dataclasses import dataclass
import math
from typing import Any, Dict

import httpx
from openai import OpenAI

import time
import utils
from utils.llm_lock import LLM_CALL_LOCK

agent_prompt = """You are an expert in Coin investing.

Analyze the provided data and decide the best action based on:
- Technical indicators and market data
- Recent news headlines and their potential impact on Coin price
- The Fear and Greed Index and its implications
- Overall market sentiment
- Patterns and trends visible in the chart data
- Insights from the YouTube transcript

Be risk-aware and prioritize capital preservation when signals are mixed or uncertain.
"""

output_schema = {
    "decision": "buy | sell | hold",
    "percentage": "integer (hold=0, buy/sell=1..100)",
    "reason": "string",
}

output_contract = """[OUTPUT CONTRACT]
- Output MUST be a single JSON object and NOTHING ELSE.
- Do NOT use markdown. Do NOT use code fences.
- Output must start with '{' and end with '}'.
- Keys must be exactly: decision, percentage, reason.
- decision must be one of: buy, sell, hold.
- If decision == 'hold', percentage MUST be 0.
- If decision in ['buy','sell'], percentage MUST be an integer 1..100.
- No additional keys.
"""

class Agent_openai:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        agent_prompt: str = agent_prompt,
        max_tokens: int = 256,   # ✅ JSON이면 보통 256이면 충분
        temperature: float = 0.1,
        timeout_connect: float = 5.0,
        timeout_read: float = 180.0,  # ✅ 로컬 LLM이면 120이 짧을 수 있어 180 권장
    ):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=httpx.Client(
                timeout=httpx.Timeout(
                    connect=timeout_connect,
                    read=timeout_read,
                    write=30.0,
                    pool=5.0,
                )
            ),
        )
        self.model = model
        self.agent_prompt = agent_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature

    def decide(self, informs: dict) -> Dict:
        system_content = (
            f"{self.agent_prompt}\n\n"
            f"{output_contract}\n\n"
            f"[JSON SCHEMA]\n{json.dumps(output_schema, ensure_ascii=False)}\n"
        )

        user_content = (
            f"[Recent coin_price]\n{informs.get('coin_price', '')}\n\n"
            f"[Recent fear_greed_index]\n{informs.get('fear_greed_index', '')}\n\n"
            f"[Recent news]\n{informs.get('news', '')}\n\n"
            f"[Recent trading reflection]\n{informs.get('reflection', '')}\n\n"
            f"[trading method transcript]\n{informs.get('youtube_transcript', '')}\n\n"
        )

        print("System content length:", len(system_content))
        print("User content length:", len(user_content))
        print("All information has been prepared. Making decision...")

        with LLM_CALL_LOCK:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)

        return {
            "decision": str(data["decision"]).strip().lower(),
            "percentage": int(data["percentage"]),
            "reason": str(data["reason"]),
        }


if __name__ == "__main__":
    t_start = time.perf_counter()
    # decision agent initialize
    agent = Agent_openai(
        base_url="http://127.0.0.1:9000/v1",
        api_key="not-used",
        model="unsloth/Mistral-Small-24B-Instruct-2501-bnb-4bit",
    )
    print("Agent initialized.")

    informs = {}

    fng = utils.get_fear_greed_index()
    informs["fear_greed_index"] = fng["value"]

    price = utils.get_price(coin_name="KRW-BTC")
    informs["coin_price"] = price

    news = utils.fetch_rss_news(feed_url="https://www.cryptobreaking.com/feed/")
    informs["news"] = news

    decision = agent.decide(informs)
    print(decision)

    t_end = time.perf_counter()
    print(f"decide elapsed: {t_end - t_start:.3f} sec")