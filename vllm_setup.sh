export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

vllm serve stelterlab/Mistral-Small-24B-Instruct-2501-AWQ \
  --host 0.0.0.0 --port 9000 \
  --quantization awq \
  --max-model-len 16384 \
  --max-num-seqs 1 \
  --max-num-batched-tokens 2048 \
  --enforce-eager
