# utils/llm_lock.py
import threading

# 로컬 vLLM(OpenAI 호환) 호출을 직렬화해서 단일 GPU 큐 밀림 방지
LLM_CALL_LOCK = threading.Lock()
