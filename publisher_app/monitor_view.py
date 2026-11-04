import threading
from queue import Empty, Queue
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import ImageTk

from .platforms.h5_monitor import DOMAINS, MonitorClient
from .storage import load_session, save_session


class MonitorLoginSupport(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.platform = tk.StringVar(value="壹料")
        self.phone = tk.StringVar()
        self.captcha_code = tk.StringVar()
        self.sms_code = tk.StringVar()
        self.interval = tk.StringVar(value="60")
        self.alert = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="请选择平台并加载关注商家")
        self.clients = {}
        self.challenges = {}
        self.tasks = {}
        self.keys = []
        self.seen = {}
        self.events = Queue()
        self.busy = False
        self.running = False
        self.timer = None
        self._build()
        self.after(100, self._poll)

    def _submit(self, title, work, done):
        if self.busy:
            self.status.set("正在处理，请稍候")
            return
        self.busy = True
        self.status.set(title + "…")

        def run():
            try:
                self.events.put((title, done, work(), None))
            except Exception as exc:
                self.events.put((title, done, None, str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            title, done, result, error = self.events.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            try:
                if error:
                    self._log(f"{title}失败：{error}")
                else:
                    self.status.set(title + "完成")
                    done(result)
            except Exception as exc:
                self._log(f"{title}处理失败：{exc}")
            finally:
                if self.running and self.timer is None:
                    self._schedule()
        self.after(100, self._poll)

    def _captcha(self):
        if self.busy:
            return
        phone = self.phone.get().strip()
        if len(phone) != 11 or not phone.isascii() or not phone.isdecimal():
            self.status.set("请输入 11 位手机号")
            return
        platform = self.platform.get()
        client = self.challenges.get(platform)
        if client is None or getattr(client, "phone", None) != phone:
            client = MonitorClient(platform)
            self.challenges[platform] = client

        def display(image):
            self.captcha_image = ImageTk.PhotoImage(image, master=self)
            self.captcha_label.configure(image=self.captcha_image)

        self._submit("获取验证码", lambda: client.captcha(phone), display)

    def _challenge(self):
        client = self.challenges.get(self.platform.get())
        if not client or getattr(client, "phone", None) != self.phone.get().strip():
            self.status.set("请先为当前平台和手机号获取验证码")
            return None
        return client

    def _send_sms(self):
        client = self._challenge()
        code = self.captcha_code.get().strip()
        if client and code:
            self._submit("发送短信", lambda: client.sms(code), lambda _: None)
