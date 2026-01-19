# agent.py
import json
from dataclasses import dataclass
from openai import OpenAI
from trade_guide import Informs, Util_Funcs, Cooltime


@dataclass
class TradingDecision:
    decision: str
    percentage: int
    reason: str

###################### prompts ######################
# ✅ agent_prompt: "분석 지침"만 남김 (출력 규칙은 아래 OUTPUT CONTRACT로 이동)
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

# ✅ JSON schema(설명용).
output_schema = {
    "decision": "buy | sell | hold",
    "percentage": "integer (hold=0, buy/sell=1..100)",
    "reason": "string"
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
##########################################################


class Agent_openai:
    def __init__(self, base_url: str, api_key: str, model: str, agent_prompt=agent_prompt,
                 max_tokens: int = 512, temperature: float = 0.1):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.agent_prompt = agent_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.output_contract = output_contract

    def decide(self, informs: Informs) -> TradingDecision:
        system_content = (
            f"{self.agent_prompt}\n\n"
            f"[Recent trading reflection]\n{informs.reflection}\n\n"
            f"[trading method transcript]\n{informs.youtube_transcript}\n\n"
            f"[OUTPUT CONTRACT]\n{self.output_contract}\n\n"
            f"[JSON SCHEMA]\n{json.dumps(output_schema, ensure_ascii=False)}\n"
        )

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": json.dumps(informs.model_input, ensure_ascii=False)},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)  # 필요 시 여기서 리트라이/검증 추가

        return TradingDecision(
            decision=data["decision"],
            percentage=int(data["percentage"]),
            reason=data["reason"],
        )

##################################################################
if __name__ == "__main__":
    snapshot = {
        "price": 68400,
        "rsi": 61.2,
        "macd": "bullish",
        "ohlcv_tail": [],
        "indicators": {"rsi": 61.2, "macd": "bullish"},
    }

    informs = Util_Funcs.make_informs(
        key="btc_v1",
        coin_name="BTC",
        video_id="-UJHObtnp5A",
        snapshot=snapshot,
        cooltime=Cooltime(),
        rss={"limit": 10, "summary_len": 300, "content_len": 600},
    )

    agent = Agent_openai(
        base_url="http://127.0.0.1:9000/v1",
        api_key="local-token",
        model="stelterlab/Mistral-Small-24B-Instruct-2501-AWQ",
        max_tokens=256, # 답변 최대 길이
        temperature=0.1,
    )

    # ✅ 여기서 바로 Informs 넣으면 됨
    decision = agent.decide(informs)

    print("=== TradingDecision ===")
    print("decision:", decision.decision)
    print("percentage:", decision.percentage)
    print("reason:", decision.reason)
