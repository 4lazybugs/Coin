
# hugging face problem
export PYTORCH_ALLOC_CONF=expandable_segments:True
vllm serve unsloth/Mistral-Small-24B-Instruct-2501-bnb-4bit \
  --host 0.0.0.0 \
  --port 9000 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 16 \
  --dtype bfloat16 \
  --enforce-eager


# stelterlab/Mistral-Small-24B-Instruct-2501-AWQ