import argparse
import yaml
import os

############ load config.yaml ########################
def load_yaml(path='config.yaml'):
    with open(path, 'r', encoding='utf-8') as f:
        raw_config = yaml.safe_load(f)

    # 환경 변수 치환 처리
    config = {}
    for k, v in raw_config.items():
        if isinstance(v, str):
            config[k] = os.path.expandvars(v)
        else:
            config[k] = v

    return config

############### get config ##########################
def get_config():
    default_cfg = load_yaml()

    parser = argparse.ArgumentParser()
    parser.add_argument("--COIN_NAME", type=str, default=default_cfg.get("COIN_NAME"))

    args = parser.parse_args()

    # Namespace -> dict + yaml 기본값 병합
    cfg = {**default_cfg, **vars(args)}
    return cfg
