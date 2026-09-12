"""Append five sample tasks; never deletes existing data."""
import json
from config import ROOT, load_agents
from taskqueue import enqueue


if __name__ == '__main__':
    tasks = json.loads((ROOT / 'sample_tasks.json').read_text(encoding='utf-8'))
    ids = [enqueue(next(iter(load_agents())), task) for task in tasks]
    print(f'Seeded {len(ids)} tasks: {ids}')
