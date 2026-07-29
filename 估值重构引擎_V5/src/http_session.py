"""HTTP Session 复用 — 防止 Windows socket 端口耗尽 (errno 22)

问题根源:
  Windows 默认动态端口约 16K 个,每个 HTTP 请求占用一个 socket,
  请求完成后 socket 进入 TIME_WAIT 状态 120s 才释放。
  估值管线 + 万业谱管线并发时,TIME_WAIT 堆积导致端口耗尽,
  新连接报 OSError [Errno 22] Invalid argument。

解决方案:
  全局共享 requests.Session,启用 HTTP keep-alive 连接复用。
  同一 host 的多次请求复用同一 TCP 连接,大幅减少 TIME_WAIT。

使用:
    from http_session import get_session
    session = get_session()
    resp = session.post(url, json=..., timeout=...)
"""

import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_lock = threading.Lock()
_session: requests.Session | None = None


def get_session() -> requests.Session:
    """获取全局共享的 HTTP Session(线程安全)。

    特性:
    - HTTP keep-alive:同一 host 复用 TCP 连接,减少 TIME_WAIT
    - 连接池: pool_maxsize=20(默认 10),支持并发
    - 自动重试: 5xx 错误 + 连接错误,指数退避
    """
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                s = requests.Session()

                # 重试策略: 连接错误/5xx 错误,指数退避
                retry = Retry(
                    total=3,
                    connect=3,
                    read=3,
                    backoff_factor=1.0,  # 1s, 2s, 4s
                    status_forcelist=(500, 502, 503, 504),
                    allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
                    raise_on_status=False,
                )

                adapter = HTTPAdapter(
                    pool_connections=20,    # 同时缓存 20 个 host 连接
                    pool_maxsize=20,        # 每个 host 最多 20 并发
                    max_retries=retry,
                    pool_block=False,       # 池满时不阻塞,新建连接
                )
                s.mount("http://", adapter)
                s.mount("https://", adapter)

                # 默认超时,防止某处忘记传 timeout
                s.request = _wrap_timeout(s.request)  # type: ignore

                _session = s
    return _session


def _wrap_timeout(orig):
    """包装 request 方法,默认 timeout=60(可被覆盖)。"""
    def wrapped(method, url, **kwargs):
        kwargs.setdefault("timeout", 60)
        return orig(method, url, **kwargs)
    return wrapped


# 兼容旧代码的便捷函数
def post(url, **kwargs):
    """等价于 requests.post,但走共享 session。"""
    return get_session().post(url, **kwargs)


def get(url, **kwargs):
    """等价于 requests.get,但走共享 session。"""
    return get_session().get(url, **kwargs)


def put(url, **kwargs):
    """等价于 requests.put,但走共享 session。"""
    return get_session().put(url, **kwargs)
