"""Authenticated LAN fire events, independent of console notification and AI."""
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import math
import queue
import threading
from urllib.parse import urlsplit

import requests

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class FireEvent:
    source_node: str
    source_epoch: float
    sequence: int
    incident_id: str
    fire_zone: str
    active: bool
    level: int
    details: str

    @classmethod
    def parse(cls, payload):
        if not isinstance(payload, dict) or set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("잘못된 경보 이벤트 필드")
        event = cls(**payload)
        for value, limit in ((event.source_node, 96), (event.incident_id, 96), (event.details, 2000)):
            if not isinstance(value, str) or not value or len(value) > limit:
                raise ValueError("잘못된 경보 문자열")
        if (event.fire_zone not in ('A', 'B', 'C') or type(event.active) is not bool
                or type(event.sequence) is not int or event.sequence < 1
                or type(event.level) is not int or event.level not in (4, 5)
                or type(event.source_epoch) not in (int, float)
                or not math.isfinite(event.source_epoch) or event.source_epoch <= 0):
            raise ValueError("잘못된 경보 값")
        return event


class FireEventLink:
    """Send local state in order, and repeat the latest state after idle periods.

    A missed recovery is retried as the latest state. Loss of communication
    never means that a previously received fire is safe.
    """
    def __init__(self, host, port, token, peers, on_event, retry_interval=5):
        if not token:
            raise ValueError("HTTP 경보 연결에는 ALERT_HTTP_TOKEN이 필요합니다")
        self.peers = []
        for peer in peers:
            parts = urlsplit(peer)
            if (parts.scheme != 'http' or not parts.hostname or parts.username or parts.password
                    or parts.path not in ('', '/') or parts.query or parts.fragment):
                raise ValueError("ALERT_HTTP_PEERS에는 http://주소:포트 형식을 사용하세요")
            self.peers.append(peer.rstrip('/'))
        self.host, self.port, self.token = host, port, token
        self.on_event = on_event
        self.retry_interval = retry_interval
        self._stop = threading.Event()
        self._queue = queue.Queue(maxsize=32)
        self._latest = None
        self._lock = threading.Lock()
        self.server = None
        self._threads = []

    def start(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.connection.settimeout(3)
                status = 400
                try:
                    if self.path != '/fire-event':
                        status = 404
                    elif not hmac.compare_digest(self.headers.get('X-Alert-Token', ''), owner.token):
                        status = 401
                    else:
                        length = int(self.headers.get('Content-Length', '0'))
                        if not 0 < length <= 16384:
                            raise ValueError('invalid size')
                        event = FireEvent.parse(json.loads(self.rfile.read(length)))
                        owner.on_event(event)
                        status = 200
                except (ValueError, TypeError, TimeoutError, OSError):
                    status = 400
                except Exception:
                    LOG.exception('HTTP 경보 처리 실패')
                    status = 500
                self.send_response(status)
                self.send_header('Content-Length', '0')
                self.end_headers()
        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        for target in (self.server.serve_forever, self._send_loop):
            thread = threading.Thread(target=target, daemon=True, name='fire-event-http')
            self._threads.append(thread)
            thread.start()
        LOG.info('구역 경보 HTTP 수신 시작: %s:%s', self.host, self.port)

    def publish(self, event):
        payload = asdict(event)
        FireEvent.parse(payload)
        with self._lock:
            self._latest = payload
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            LOG.warning('경보 전송 대기열 초과; 최신 상태를 다음 재전송 때 전달합니다')

    def _send_loop(self):
        while not self._stop.is_set():
            queued = False
            try:
                payload = self._queue.get(timeout=self.retry_interval)
                queued = True
            except queue.Empty:
                with self._lock:
                    payload = self._latest
            try:
                if payload and not self._stop.is_set():
                    for peer in self.peers:
                        try:
                            response = requests.post(peer+'/fire-event', json=payload,
                                headers={'X-Alert-Token': self.token}, timeout=(2, 3))
                            response.raise_for_status()
                        except requests.RequestException as exc:
                            LOG.warning('구역 경보 HTTP 전송 실패 (%s); 최신 상태 재전송 예정', type(exc).__name__)
            finally:
                if queued:
                    self._queue.task_done()

    def close(self):
        self._stop.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        for thread in self._threads:
            thread.join(timeout=1)
