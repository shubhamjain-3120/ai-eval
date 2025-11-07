# Gunicorn configuration file
import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 2048

# Worker processes
workers = 1  # Use only 1 worker on free tier to save memory
worker_class = "sync"
worker_connections = 1000
timeout = 180  # Increase timeout to 3 minutes for OpenAI API calls with queuing
keepalive = 5

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "rfp-evaluation-tool"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Memory optimization
max_requests = 1000  # Restart worker after this many requests
max_requests_jitter = 50  # Add randomness to prevent all workers restarting at once

# Graceful timeout
graceful_timeout = 30

