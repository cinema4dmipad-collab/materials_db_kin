import os

bind = os.getenv('GUNICORN_BIND', '0.0.0.0:8000')
workers = int(os.getenv('GUNICORN_WORKERS', '2'))
threads = int(os.getenv('GUNICORN_THREADS', '1'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '3600'))
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '3600'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '5'))
limit_request_line = 8190
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
