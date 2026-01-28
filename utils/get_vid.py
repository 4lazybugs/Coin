import os
import time
import traceback
from youtube_transcript_api import YouTubeTranscriptApi
from openai import OpenAI

from .llm_lock import LLM_CALL_LOCK  # ✅ 단일 GPU 직렬화

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

DEFAULT_MODEL = "unsloth/Mistral-Small-24B-Instruct-2501-bnb-4bit"


def get_vid_script(base_url: str, api_key: str, video_id: str) -> str:
    model = os.getenv("LOCAL_OPENAI_MODEL_YOUTUBE", DEFAULT_MODEL)

    # ✅ youtube는 heavy 작업이라 timeout 별도 권장
    timeout_s = float(os.getenv("LOCAL_OPENAI_TIMEOUT_YOUTUBE", "180"))

    # ✅ 입력/출력 축소(속도/안정성에 직결)
    max_chars = int(os.getenv("YOUTUBE_TRANSCRIPT_MAX_CHARS", "8000"))
    max_out_tokens = int(os.getenv("YOUTUBE_STRATEGY_MAX_TOKENS", "400"))

    # 1) youtube transcript
    t0 = time.perf_counter()
    fetched_transcript = YouTubeTranscriptApi().fetch(video_id)
    full_text = " ".join([snippet.text for snippet in fetched_transcript])
    print(f"[TIMING] youtube transcript fetch: {(time.perf_counter()-t0):.3f}s")
    print("[DEBUG] transcript chars (raw):", len(full_text))

    # 2) 입력 길이 제한
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]
    print("[DEBUG] transcript chars (clipped):", len(full_text))

    # 3) local LLM client
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        max_retries=0,
        timeout=timeout_s,
    )

    # 4) 변환 (락 + 스트리밍)
    t1 = time.perf_counter()
    try:
        with LLM_CALL_LOCK:
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": full_text},
                ],
                temperature=0.1,
                max_tokens=max_out_tokens,
                stream=True,  # ✅ ReadTimeout(첫 바이트 지연) 방지에 매우 유효
            )

        chunks = []
        for ev in stream:
            if not ev.choices:
                continue
            delta = ev.choices[0].delta.content
            if delta:
                chunks.append(delta)

        return "".join(chunks).strip()

    except Exception as e:
        # ✅ 실패해도 전체 파이프라인이 죽지 않게: 빈 문자열 반환
        print("[ERROR] youtube LLM call failed:", repr(e))
        print(traceback.format_exc())
        return ""

    finally:
        print(f"[TIMING] youtube LLM call: {(time.perf_counter()-t1):.3f}s")


if __name__ == "__main__":
    API_KEY = "local-token"
    BASE_URL = "http://127.0.0.1:9000/v1"

    # 실행 전 권장:
    # export LOCAL_OPENAI_TIMEOUT_YOUTUBE=180
    # export YOUTUBE_TRANSCRIPT_MAX_CHARS=8000
    # export YOUTUBE_STRATEGY_MAX_TOKENS=400

    out = get_vid_script(base_url=BASE_URL, api_key=API_KEY, video_id="F_HVfz_IcgY")
    print(out)
