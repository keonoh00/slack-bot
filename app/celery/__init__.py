from celery import Celery

from app.config.env import env

celeryApp = Celery("ksignChatbot", broker=env.redis.url, include=["app.celery.tasks"])
