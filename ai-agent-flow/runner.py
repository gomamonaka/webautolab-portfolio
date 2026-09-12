"""Drain one stage, including bounded retries. No network in stub mode."""
import argparse
import json
import os
import subprocess
import tempfile
import urllib.request
from config import ROOT, load_agents
from taskqueue import claim_next, complete, fail


def generate(provider, agent, payload):
    if provider == 'stub':
        return {k: f'STUB {agent["name"]}: {payload.get("topic", "demo")}'
                for k in agent['output_contract']}
    prompt = agent['prompt_template'].replace('{payload}', json.dumps(payload, ensure_ascii=False))
    prompt += '\nReturn only a JSON object with these required keys: ' + json.dumps(agent['output_contract'])
    if provider == 'codex':
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, 'result.json')
            args = ['codex', 'exec', '--sandbox', 'read-only', '-C', str(ROOT),
                    '--skip-git-repo-check', '--ephemeral', '-o', output, prompt]
            subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           check=True, timeout=180)
            with open(output, encoding='utf-8') as stream:
                return json.load(stream)
    if provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        headers = {'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']}
        body = {'model': os.environ['OPENAI_MODEL'], 'input': prompt, 'store': False}
    elif provider == 'anthropic':
        url = 'https://api.anthropic.com/v1/messages'
        headers = {'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}
        body = {'model': os.environ['ANTHROPIC_MODEL'], 'max_tokens': 2048,
                'messages': [{'role': 'user', 'content': prompt}]}
    else:
        raise ValueError('Unknown provider')
    headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)
    if provider == 'openai':
        text = ''.join(c['text'] for item in data.get('output', [])
                       for c in item.get('content', []) if c.get('type') == 'output_text')
    else:
        text = ''.join(c['text'] for c in data['content'] if c['type'] == 'text')
    return json.loads(text)


def run_stage(stage, provider):
    agent = load_agents()[stage]
    attempts = failed = 0
    while (task := claim_next(stage)) is not None:
        attempts += 1
        try:
            payload = json.loads(task['payload'])
            missing = set(agent['input_contract']) - payload.keys()
            if missing:
                raise ValueError('Missing required keys: ' + ', '.join(sorted(missing)))
            result = generate(provider, agent, payload)
            complete(task['id'], result, agent['next_stage'])
        except Exception as exc:
            # Do not persist provider response bodies or command arguments (may contain data).
            error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            status = fail(task['id'], error)
            failed += status == 'failed'
            print(f'task={task["id"]} stage={stage} status={status} error={error}')
    print(f'{stage}: attempts={attempts} terminal_failed={failed}')
    return failed


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--provider', choices=['stub', 'codex', 'openai', 'anthropic'], default='stub')
    return result


if __name__ == '__main__':
    cli = parser()
    cli.add_argument('--stage', required=True, choices=list(load_agents()))
    args = cli.parse_args()
    raise SystemExit(1 if run_stage(args.stage, args.provider) else 0)
