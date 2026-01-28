nohup sh vllm_setup.sh > vllm.log 2>&1 &
nohup python auto_trade_test.py > trade.log 2>&1 &