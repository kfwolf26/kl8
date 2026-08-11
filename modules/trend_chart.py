import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser


class TrendChart:
    def __init__(self, parent):
        self.parent = parent
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self.parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        title_label = ttk.Label(frame, text="📈 福彩快乐8走势图", font=("微软雅黑", 16, "bold"))
        title_label.pack(pady=20)

        desc_label = ttk.Label(frame, text="点击下方按钮打开走势图（1-80，每期开20个号码）", font=("微软雅黑", 11))
        desc_label.pack(pady=10)

        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=30)

        btn1 = tk.Button(button_frame, text="  🎯 快乐8走势图(中彩网)  ", bg="#5cb85c", fg="white",
                         relief=tk.RAISED, padx=10, pady=8, font=("微软雅黑", 11, "bold"),
                         command=lambda: self._open_url("https://chart.zhcw.com/zst/kl8.html"),
                         width=22)
        btn1.pack(pady=10)

        btn2 = tk.Button(button_frame, text="  🎯 快乐8走势图(500彩票)  ", bg="#d9534f", fg="white",
                         relief=tk.RAISED, padx=10, pady=8, font=("微软雅黑", 11, "bold"),
                         command=lambda: self._open_url("https://kaijiang.500.com/kl8.shtml"),
                         width=22)
        btn2.pack(pady=10)

        btn3 = tk.Button(button_frame, text="  🎯 快乐8开奖(福彩官网)  ", bg="#5bc0de", fg="white",
                         relief=tk.RAISED, padx=10, pady=8, font=("微软雅黑", 11, "bold"),
                         command=lambda: self._open_url("https://www.cwl.gov.cn/ygkj/wqkj/kl8/"),
                         width=22)
        btn3.pack(pady=10)

        status_label = ttk.Label(frame, text="", font=("微软雅黑", 10), foreground="green")
        status_label.pack(pady=10)
        self.status_label = status_label

    def _open_url(self, url):
        try:
            webbrowser.open(url)
            self.status_label.config(text=f"已打开：{url}")
        except Exception as e:
            messagebox.showerror("错误", f"打开失败: {str(e)}")
            self.status_label.config(text="打开失败", foreground="red")
