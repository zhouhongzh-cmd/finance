import queue
import threading
from typing import Optional

import httpx

from models.signals import Signal
from config.settings import settings
from utils.db_manager import DBManager
from utils.logger import logger


class Notifier:
    """提供单例式异步内存发送队列，避免 Webhook 卡死所有策略主线程"""

    def __init__(self):
        self.q = queue.Queue()
        self.client = httpx.Client(timeout=settings.REQUEST_TIMEOUT)
        self.db_manager = DBManager()
        self._start_worker()

    def _start_worker(self):
        worker = threading.Thread(target=self._process_queue, daemon=True)
        worker.start()

    def _process_queue(self):
        while True:
            signal: Signal = self.q.get()
            try:
                self._deliver(signal)
            except Exception as e:
                logger.error("notification_failed", error=str(e))
            finally:
                self.q.task_done()

    def send(self, signal: Signal):
        """主入口：各 AI 开发的策略只能调用这里！"""
        self.q.put(signal)

    def flush(self):
        """测试或关闭前等待队列处理完成。"""
        self.q.join()

    def _deliver(self, signal: Signal):
        sent_channels = []

        if settings.FEISHU_WEBHOOK_URL:
            try:
                self._send_feishu(signal)
                sent_channels.append("feishu")
            except Exception as exc:
                logger.error(
                    "notification_channel_failed",
                    channel="feishu",
                    error=str(exc),
                    strategy=signal.strategy_name,
                    asset=signal.asset,
                )

        if settings.WECOM_WEBHOOK_URL:
            try:
                self._send_wecom(signal)
                sent_channels.append("wecom")
            except Exception as exc:
                logger.error(
                    "notification_channel_failed",
                    channel="wecom",
                    error=str(exc),
                    strategy=signal.strategy_name,
                    asset=signal.asset,
                )

        if not sent_channels:
            logger.info(
                "skip_notification",
                msg="No notification channel configured",
                data=signal.message,
            )
            return

        if signal.alert_id is not None:
            self.db_manager.mark_alert_notified(signal.alert_id)

        logger.info(
            "notification_delivered",
            strategy=signal.strategy_name,
            level=signal.level,
            asset=signal.asset,
            channels=sent_channels,
            alert_id=signal.alert_id,
        )

    def _send_feishu(self, signal: Signal):
        color_map = {"INFO": "blue", "WARNING": "yellow", "CRITICAL": "red"}
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"[{signal.level}] {signal.strategy_name}",
                    },
                    "template": color_map.get(signal.level, "blue"),
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": signal.message,
                        },
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": f"标的: {signal.asset}",
                            }
                        ],
                    },
                ],
            },
        }
        self._post_json(settings.FEISHU_WEBHOOK_URL, payload)
        logger.info(
            "sent_notification",
            channel="feishu",
            strategy=signal.strategy_name,
            level=signal.level,
            asset=signal.asset,
        )

    def _send_wecom(self, signal: Signal):
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": (
                    f"**[{signal.level}] {signal.strategy_name}**\n"
                    f"> 标的: `{signal.asset}`\n"
                    f"> 时间: `{signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
                    f"{signal.message}"
                )
            },
        }
        self._post_json(settings.WECOM_WEBHOOK_URL, payload)
        logger.info(
            "sent_notification",
            channel="wecom",
            strategy=signal.strategy_name,
            level=signal.level,
            asset=signal.asset,
        )

    def _post_json(self, url: str, payload: dict):
        response = self.client.post(url, json=payload)
        response.raise_for_status()
        return response


_notifier_instance: Optional[Notifier] = None
_notifier_lock = threading.Lock()


def get_notifier() -> Notifier:
    global _notifier_instance
    if _notifier_instance is None:
        with _notifier_lock:
            if _notifier_instance is None:
                _notifier_instance = Notifier()
    return _notifier_instance


class LazyNotifierProxy:
    """延迟初始化通知器，避免模块导入时启动线程和 HTTP 客户端。"""

    def __getattr__(self, name):
        return getattr(get_notifier(), name)

    def __setattr__(self, name, value):
        setattr(get_notifier(), name, value)


notifier = LazyNotifierProxy()
