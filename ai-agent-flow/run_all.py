"""Invoke each stage in order once; each invocation drains that stage."""
from config import load_agents
from taskqueue import counts
from runner import parser, run_stage


def main():
    args = parser().parse_args()
    for stage in load_agents():
        run_stage(stage, args.provider)
    summary = counts()
    print('SUMMARY ' + ' '.join(f'{key}={value}' for key, value in summary.items()))
    return 1 if summary['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
