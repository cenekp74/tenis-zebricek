from flask import render_template
from app.tasks import send_email


def queue_email(subject, recipients, template, reply_to=None, **context):
    html = render_template(f'email/{template}', **context)
    send_email.delay(subject, recipients, html, reply_to=reply_to)
