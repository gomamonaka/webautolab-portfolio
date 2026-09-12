"""Best-effort notification: SMTP with a local fallback, never raises."""
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from config import ROOT


def notify_failure(task_id, stage, error):
    record = {'task_id': task_id, 'stage': stage, 'error': error}
    try:
        host, sender, recipient = (os.getenv(k) for k in ('SMTP_HOST', 'SMTP_FROM', 'SMTP_TO'))
        if not all((host, sender, recipient)):
            raise ValueError('SMTP settings unset')
        message = EmailMessage()
        message['Subject'] = f'Pipeline failed: task {task_id} / {stage}'
        message['From'], message['To'] = sender, recipient
        message.set_content(json.dumps(record, ensure_ascii=False))
        with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587')), timeout=10) as smtp:
            if os.getenv('SMTP_STARTTLS', '1') == '1':
                smtp.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
        return
    except Exception as exc:
        record['notification_error'] = type(exc).__name__
    try:
        with (ROOT / 'notifications.log').open('a', encoding='utf-8') as log:
            log.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception:
        try:
            print('Notification delivery and log write failed', file=sys.stderr)
        except Exception:
            pass
