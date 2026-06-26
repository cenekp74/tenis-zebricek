from celery import Celery
from flask_mail import Message

celery = Celery('app')


def make_celery(flask_app):
    celery.conf.broker_url = flask_app.config['CELERY_BROKER_URL']
    celery.conf.result_backend = flask_app.config['CELERY_RESULT_BACKEND']

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


@celery.task
def send_email(subject, recipients, html_body, text_body=None):
    from app import mail
    msg = Message(subject, recipients=recipients)
    msg.html = html_body
    if text_body:
        msg.body = text_body
    mail.send(msg)
