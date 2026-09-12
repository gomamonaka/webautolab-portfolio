"""Paths and validated, declarative agent configuration."""
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('PIPELINE_DB', ROOT / 'pipeline.db'))


def load_agents():
    agents = yaml.safe_load((ROOT / 'agents.yaml').read_text(encoding='utf-8'))['agents']
    names = [a['name'] for a in agents]
    orders = [a['stage'] for a in agents]
    if len(set(names)) != len(names) or len(set(orders)) != len(orders):
        raise ValueError('Agent names and stage orders must be unique')
    by_name = {a['name']: a for a in agents}
    for a in agents:
        if type(a['stage']) is not int or type(a['max_retries']) is not int or a['max_retries'] < 0:
            raise ValueError('stage must be integer; max_retries must be nonnegative')
        for key in ('input_contract', 'output_contract'):
            if not isinstance(a[key], list) or not all(isinstance(k, str) for k in a[key]):
                raise ValueError(f'{key} must be a list of keys')
        if not isinstance(a['prompt_template'], str):
            raise ValueError('prompt_template must be text')
        nxt = a['next_stage']
        if nxt is not None and (nxt not in by_name or by_name[nxt]['stage'] <= a['stage']):
            raise ValueError('next_stage must name a later stage')
        if nxt and not set(by_name[nxt]['input_contract']) <= set(a['input_contract'] + a['output_contract']):
            raise ValueError(f'Contracts do not connect: {a["name"]} -> {nxt}')
    return dict(sorted(by_name.items(), key=lambda item: item[1]['stage']))
