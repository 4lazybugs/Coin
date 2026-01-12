from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


# https://www.youtube.com/watch?v=r7tov49OT3Y: Watch THESE CRYPTOS In 2026!!
video_id_01 = "r7tov49OT3Y"
# https://www.youtube.com/shorts/5CfV4Afi1F4: 코인 단타 매매기법
video_id_02 = "5CfV4Afi1F4"
# https://www.youtube.com/watch?v=6itriowPhhM: 코인 매매기법 (10만원 -> 9,000만원)
video_id_03 = "6itriowPhhM"

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

client = ChatOpenAI(
    api_key=api_key,
    model="gpt-4o",
    temperature=0.0,
)

SYSTEM_PROMPT = """You are an expert prompt engineer for trading systems.

Your task is to rewrite the given YouTube transcript into an INVESTMENT STRATEGY DESCRIPTION
that can be used directly as a system prompt for a Bitcoin trading analyst.

Rules:
- Do NOT summarize mechanically.
- Extract the implied investment philosophy, trading style, risk attitude, and time horizon.
- Write in professional, declarative language.
- The output MUST read as an analyst's guiding strategy, not as a transcript.
- Do NOT include buy/sell decisions.
- Output plain text only.
"""



def get_vid_script(video_id: str) -> str:
    ytt_api = YouTubeTranscriptApi()
    #fetched_transcript = ytt_api.fetch(video_id)
    fetched_transcript = ytt_api.fetch(video_id, languages=['ko'])

    # text만 추출해서 하나의 문자열로 결합
    full_text = " ".join([snippet.text for snippet in fetched_transcript])
    #print(full_text01)

    response = client.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=full_text),
    ])
    script = response.content
    
    return script