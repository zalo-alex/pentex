import logging
import os
import time
from logging.handlers import RotatingFileHandler

from flask import g, request

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'pentex.log')

# Brand red used across the UI (see static/css/base.css)
_PENTEX_RED = '\033[38;2;196;30;58m'
_DIM = '\033[2m'
_RESET = '\033[0m'
_SUBTITLE = 'Penetration Testing Report Manager'
_INDENT = '  '

_ART = [
    ' ____  _____ _   _ _____ _______  __',
    '|  _ \\| ____| \\ | |_   _| ____\\ \\/ /',
    '| |_) |  _| |  \\| | | | |  _|  \\  / ',
    '|  __/| |___| |\\  | | | | |___ /  \\ ',
    '|_|   |_____|_| \\_| |_| |_____/_/\\_\\',
]


def print_banner():
    art = '\n'.join(_INDENT + line for line in _ART)
    print(f'{_PENTEX_RED}\n{art}{_RESET}')
    print(f'{_DIM}{_INDENT}{_SUBTITLE}{_RESET}\n')


def configure_logging(app):
    """Wire up console + rotating file logging and log every request.

    socketio.run() only emits werkzeug's access log when app.debug is True,
    so without this the server produces no output at all in normal use.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    level = getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s', '%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    app.logger.setLevel(level)
    # The dev/gevent server's own access logging is redundant with the
    # after_request logging below, so keep it quiet unless something's wrong.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('geventwebsocket.handler').setLevel(logging.WARNING)

    @app.before_request
    def _log_request_start():
        g._request_start_time = time.time()

    @app.after_request
    def _log_request(response):
        start = getattr(g, '_request_start_time', None)
        duration_ms = int((time.time() - start) * 1000) if start is not None else '?'
        try:
            from flask_login import current_user
            user = current_user.username if current_user.is_authenticated else '-'
        except Exception:
            user = '-'
        app.logger.info(
            '%s %s %s %sms user=%s ip=%s',
            request.method, request.path, response.status_code,
            duration_ms, user, request.remote_addr,
        )
        return response

    return app.logger
