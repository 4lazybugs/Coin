export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# max-model-len: 입력 컨텍스트 최대 길이
vllm serve stelterlab/Mistral-Small-24B-Instruct-2501-AWQ \
  --host 0.0.0.0 --port 9000 \
  --quantization awq \
  --max-model-len 32768 \
  --max-num-seqs 1 \
  --max-num-batched-tokens 2048 \
  --gpu-memory-utilization 0.90 \
  --enforce-eager

