import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import random
import threading
from utils.history_manager import HistoryManager


NUM_ALL = list(range(1, 81))   # 快乐8 号码池 1-80


def _parse_result(result_str):
    """解析 'n1,n2,...,n20' → list[int]（20个开奖号码）。"""
    if not result_str:
        return []
    try:
        return [int(x) for x in result_str.split(",")]
    except Exception:
        return []


# 福彩快乐8 选十奖级表：命中数 → (奖级名, 奖金元)
XUANSHI_PRIZE_TABLE = {
    10: ("一等奖", 5_000_000),
    9: ("二等奖", 8_000),
    8: ("三等奖", 800),
    7: ("四等奖", 80),
    6: ("五等奖", 5),
    5: ("六等奖", 3),
    0: ("安慰奖", 2),
}


def _xuanshi_prize(hit_count):
    """根据选十命中数(0-10)返回 (奖级描述, 奖金元)。中1-4为无奖。"""
    if hit_count in XUANSHI_PRIZE_TABLE:
        name, money = XUANSHI_PRIZE_TABLE[hit_count]
        return f"{name}({money:,}元)", money
    return "无奖", 0


def _compute_bet(next_predictors, remain):
    """从下一期所有预测者的选号中统计频率，在剩余号码(remain)范围内取频率最高的10个作为选十码。
    若remain不足10个，则从非remain号码中按频率补足至10个。返回排序后的10个号码列表。"""
    from collections import Counter
    freq = Counter()
    for pred in next_predictors:
        for n in pred.get("numbers", []):
            freq[n] += 1
    remain_set = set(remain)
    # 优先从remain中按频率降序、号码升序取
    in_remain = sorted(remain, key=lambda n: (-freq.get(n, 0), n))
    bet = list(in_remain[:10])
    # 不足10个则从非remain中补足
    if len(bet) < 10:
        out_remain = sorted(
            (n for n in range(1, 81) if n not in remain_set),
            key=lambda n: (-freq.get(n, 0), n)
        )
        for n in out_remain:
            if len(bet) >= 10:
                break
            bet.append(n)
    return sorted(bet[:10])


class PredictionModel:
    def __init__(self, parent):
        self.parent = parent
        self.root = parent.winfo_toplevel()
        self.history_manager = HistoryManager()
        self.prediction_data = {}
        self.prediction_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "prediction_data.json"
        )
        self.saved_predictions_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "saved_predictions.json"
        )
        self.saved_predictions = []
        self.status_var = tk.StringVar(value="")
        self.current_bet = []   # 当前选十码（10个号码），由计算杀号时生成
        self.settings_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "prediction_settings.json"
        )

        self.settings = self._load_settings()
        self._load_prediction_data()
        self._load_saved_predictions()
        self._build_ui()

    def _load_prediction_data(self):
        if os.path.exists(self.prediction_file):
            try:
                with open(self.prediction_file, 'r', encoding='utf-8') as f:
                    self.prediction_data = json.load(f)
            except Exception:
                self.prediction_data = {}

    def _save_prediction_data(self):
        try:
            with open(self.prediction_file, 'w', encoding='utf-8') as f:
                json.dump(self.prediction_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _is_legacy_data(self):
        """检测 prediction_data 是否为旧结构（DLT的front/back 而非 numbers）。"""
        if not self.prediction_data or "predictions" not in self.prediction_data:
            return False
        params = self.prediction_data.get("params", {})
        # 旧结构有 front_count/back_count 无 num_count
        if ("front_count" in params or "back_count" in params) and "num_count" not in params:
            return True
        predictions = self.prediction_data.get("predictions", {})
        for pred_data in predictions.values():
            predictors = pred_data.get("predictors", [])
            if predictors:
                first = predictors[0]
                if "front" in first or "back" in first:
                    if "numbers" not in first:
                        return True
                break
        return False

    def _load_saved_predictions(self):
        if os.path.exists(self.saved_predictions_file):
            try:
                with open(self.saved_predictions_file, 'r', encoding='utf-8') as f:
                    self.saved_predictions = json.load(f)
            except Exception:
                self.saved_predictions = []
        else:
            self.saved_predictions = []

    def _save_saved_predictions(self):
        try:
            with open(self.saved_predictions_file, 'w', encoding='utf-8') as f:
                json.dump(self.saved_predictions, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _load_settings(self):
        """从 settings 文件加载参数设置，返回 dict。"""
        defaults = {
            "predictor_count": "5000",
            "num_count": "10",
            "min_streak": "3",
            "predict_periods": "30",
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    defaults.update({k: str(v) for k, v in data.items()})
            except Exception:
                pass
        return defaults

    def _save_settings(self):
        """把当前参数设置保存到 settings 文件。"""
        settings = {
            "predictor_count": self.predictor_count_var.get().strip(),
            "num_count": self.num_count_var.get().strip(),
            "min_streak": self.min_streak_var.get().strip(),
            "predict_periods": self.predict_periods_var.get().strip(),
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            self.settings = settings
            return True
        except Exception:
            return False

    def _on_save_settings(self):
        """保存设置按钮回调：校验参数并持久化。"""
        try:
            pc = int(self.predictor_count_var.get().strip())
            nc = int(self.num_count_var.get().strip())
            ms = int(self.min_streak_var.get().strip())
            pp = int(self.predict_periods_var.get().strip())
        except ValueError:
            messagebox.showerror("错误", "参数必须为整数，请检查输入")
            return
        if pc <= 0 or pp <= 0:
            messagebox.showerror("错误", "预测者数量和预测期数必须大于0")
            return
        if nc <= 0 or nc > 80:
            messagebox.showerror("错误", "每预测者号码数量必须在1-80之间")
            return
        if ms <= 0:
            messagebox.showerror("错误", "最小连续命中期数必须大于0")
            return
        if self._save_settings():
            messagebox.showinfo("成功", "参数设置已保存，下次启动自动加载")
        else:
            messagebox.showerror("错误", "设置保存失败，请检查文件权限")

    def _refresh_saved_list(self):
        total = len(self.saved_predictions)
        opened = len([r for r in self.saved_predictions if r.get("result")])
        pending = total - opened
        self.stats_label.config(
            text=f"已保存 {total} 期预测记录（已开奖 {opened} 期，待开奖 {pending} 期），点击\"预测对错统计\"查看详情"
        )

    def _build_ui(self):
        # 外层容器：Canvas + 垂直滚动条（解决内容过高导致下方看不见/无法下拉的问题）
        outer = ttk.Frame(self.parent)
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0, bg="white")
        self._pm_scroll_canvas = canvas
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        hsb = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        # 真正的内容主容器（放置到 Canvas 中，作为可滚动区域）
        main_frame = ttk.Frame(canvas)
        self._pm_scroll_content = main_frame
        main_win = canvas.create_window((0, 0), window=main_frame, anchor="nw")

        def _on_content_configure(_evt, c=canvas):
            c.configure(scrollregion=c.bbox("all"))

        def _on_canvas_configure(evt, c=canvas, win=main_win):
            # 使内容宽度随窗口变化，避免内容区被固定死宽度
            c.itemconfigure(win, width=evt.width)

        main_frame.bind("<Configure>", _on_content_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # 鼠标滚轮滚动（Windows/Linux/macOS 适配）
        def _bind_mousewheel(widget, c=canvas):
            def _on_wheel(evt):
                c.yview_scroll(int(-1 * (evt.delta / 120)), "units")
            def _on_button4(_evt):
                c.yview_scroll(-1, "units")
            def _on_button5(_evt):
                c.yview_scroll(1, "units")
            widget.bind_all("<MouseWheel>", _on_wheel, add="+")
            widget.bind_all("<Button-4>", _on_button4, add="+")
            widget.bind_all("<Button-5>", _on_button5, add="+")
        _bind_mousewheel(canvas)

        # 参数设置
        param_frame = ttk.LabelFrame(main_frame, text="参数设置", padding=8)
        param_frame.pack(fill=tk.X, pady=(0, 8))

        param_row = ttk.Frame(param_frame)
        param_row.pack(fill=tk.X)

        ttk.Label(param_row, text="预测者数量：").pack(side=tk.LEFT, padx=(5, 2), pady=5)
        self.predictor_count_var = tk.StringVar(value=self.settings.get("predictor_count", "5000"))
        ttk.Entry(param_row, textvariable=self.predictor_count_var, width=10).pack(side=tk.LEFT, padx=(2, 10), pady=5)

        ttk.Label(param_row, text="每预测者号码数量：").pack(side=tk.LEFT, padx=2, pady=5)
        self.num_count_var = tk.StringVar(value=self.settings.get("num_count", "10"))
        ttk.Entry(param_row, textvariable=self.num_count_var, width=6).pack(side=tk.LEFT, padx=(2, 10), pady=5)

        ttk.Label(param_row, text="最小连续命中期数：").pack(side=tk.LEFT, padx=2, pady=5)
        self.min_streak_var = tk.StringVar(value=self.settings.get("min_streak", "3"))
        ttk.Entry(param_row, textvariable=self.min_streak_var, width=6).pack(side=tk.LEFT, padx=(2, 10), pady=5)

        ttk.Label(param_row, text="预测期数：").pack(side=tk.LEFT, padx=2, pady=5)
        self.predict_periods_var = tk.StringVar(value=self.settings.get("predict_periods", "30"))
        ttk.Entry(param_row, textvariable=self.predict_periods_var, width=6).pack(side=tk.LEFT, padx=(2, 10), pady=5)

        tk.Button(param_row, text="  🔄 应用参数并生成预测数据  ", bg="#5bc0de", fg="white",
                  relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                  command=self._generate_predictions).pack(side=tk.LEFT, padx=6, pady=8)

        self.btn_add_predict = tk.Button(param_row, text="  ➕ 补齐预测  ", bg="#f0ad4e", fg="white",
                                         relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                                         command=self._add_predictions)
        self.btn_add_predict.pack(side=tk.LEFT, padx=6, pady=8)

        self.btn_save_settings = tk.Button(param_row, text="  💾 保存设置  ", bg="#9b59b6", fg="white",
                                           relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                                           command=self._on_save_settings)
        self.btn_save_settings.pack(side=tk.LEFT, padx=6, pady=8)

        # 查询区
        query_frame = ttk.LabelFrame(main_frame, text="查询预测数据", padding=8)
        query_frame.pack(fill=tk.X, pady=(0, 8))

        query_row = ttk.Frame(query_frame)
        query_row.pack(fill=tk.X)

        ttk.Label(query_row, text="预测者ID：").pack(side=tk.LEFT, padx=(5, 2), pady=5)
        self.query_pid_var = tk.StringVar(value="1")
        ttk.Entry(query_row, textvariable=self.query_pid_var, width=10).pack(side=tk.LEFT, padx=(2, 10), pady=5)

        tk.Button(query_row, text="  🔍 查询该预测者所有期预测数据  ", bg="#5cb85c", fg="white",
                  relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                  command=self._query_predictor_data).pack(side=tk.LEFT, padx=10, pady=5)

        tk.Button(query_row, text="  🔄 刷新开奖结果  ", bg="#f0ad4e", fg="white",
                  relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                  command=self._refresh_results).pack(side=tk.LEFT, padx=6, pady=5)

        self.btn_calc_kill = tk.Button(query_row, text="  ⚡ 计算杀号  ", bg="#d9534f", fg="white",
                                       relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9, "bold"),
                                       command=self._calculate_kill_numbers)
        self.btn_calc_kill.pack(side=tk.LEFT, padx=6, pady=5)

        # 预测者历史数据
        self.query_result_frame = ttk.LabelFrame(main_frame, text="预测者历史数据", padding=5)
        self.query_result_frame.pack(fill=tk.X, pady=(0, 8))

        query_columns = ("issue", "result", "prediction", "hit")
        self.query_tree = ttk.Treeview(self.query_result_frame, columns=query_columns, show="headings", height=5)
        self.query_tree.heading("issue", text="期号")
        self.query_tree.heading("result", text="开奖号")
        self.query_tree.heading("prediction", text="预测号码")
        self.query_tree.heading("hit", text="命中")
        self.query_tree.column("issue", width=90, anchor=tk.CENTER)
        self.query_tree.column("result", width=260, anchor=tk.CENTER)
        self.query_tree.column("prediction", width=260, anchor=tk.CENTER)
        self.query_tree.column("hit", width=60, anchor=tk.CENTER)

        self.query_tree.tag_configure("hit_row", foreground="#d32f2f")
        self.query_tree.tag_configure("pending", foreground="#999999")
        self.query_tree.tag_configure("result_blue", foreground="#1976d2")

        query_scrollbar = ttk.Scrollbar(self.query_result_frame, orient=tk.VERTICAL, command=self.query_tree.yview)
        self.query_tree.configure(yscrollcommand=query_scrollbar.set)
        self.query_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        query_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 杀号结果 + 剩余号码（单栏全宽，位于外层可滚动容器内，不再 expand 避免挤压其他部件）
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.X)

        kill_frame = ttk.LabelFrame(content_frame, text="杀号结果", padding=5)
        kill_frame.pack(fill=tk.X, pady=(0, 5))

        self.kill_label = ttk.Label(kill_frame,
                                    text="杀号对应预测期数：- | 杀号条目数：0 | 去重后杀号数：0")
        self.kill_label.pack(anchor=tk.W, pady=(0, 5))

        kill_cols = ("predictor_id", "seq", "kill_num", "streak", "hit_rate")
        self.kill_tree = ttk.Treeview(kill_frame, columns=kill_cols, show="headings", height=6)
        self.kill_tree.heading("predictor_id", text="预测者ID")
        self.kill_tree.heading("seq", text="序号")
        self.kill_tree.heading("kill_num", text="杀号数字")
        self.kill_tree.heading("streak", text="连续命中期数")
        self.kill_tree.heading("hit_rate", text="历史命中率")
        self.kill_tree.column("predictor_id", width=80, anchor=tk.CENTER)
        self.kill_tree.column("seq", width=60, anchor=tk.CENTER)
        self.kill_tree.column("kill_num", width=100, anchor=tk.CENTER)
        self.kill_tree.column("streak", width=120, anchor=tk.CENTER)
        self.kill_tree.column("hit_rate", width=120, anchor=tk.CENTER)

        kill_scroll = ttk.Scrollbar(kill_frame, orient=tk.VERTICAL, command=self.kill_tree.yview)
        self.kill_tree.configure(yscrollcommand=kill_scroll.set)
        self.kill_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        kill_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        remain_frame = ttk.LabelFrame(content_frame, text="剩余号码（1-80 去除杀号）", padding=5)
        remain_frame.pack(fill=tk.X)
        self.remain_label = ttk.Label(remain_frame, text="剩余号码总数：80")
        self.remain_label.pack(anchor=tk.W, pady=(0, 5))
        self.remain_text = tk.Text(remain_frame, height=3, bg="white", relief=tk.SUNKEN,
                                   font=("微软雅黑", 10), wrap=tk.WORD)
        self.remain_text.pack(fill=tk.X)
        self.remain_text.insert(tk.END, " ".join(f"{n:02d}" for n in NUM_ALL))
        self.remain_text.config(state=tk.DISABLED)

        bet_frame = ttk.LabelFrame(content_frame, text="选十码（取剩余号码中预测者共识最高的10个，用于评估奖级）", padding=5)
        bet_frame.pack(fill=tk.X, pady=(5, 0))
        self.bet_label = ttk.Label(bet_frame, text="选十码：尚未计算（请先点击\"计算杀号\"）")
        self.bet_label.pack(anchor=tk.W, pady=(0, 5))
        self.bet_text = tk.Text(bet_frame, height=2, bg="white", relief=tk.SUNKEN,
                                font=("微软雅黑", 11, "bold"), wrap=tk.WORD, foreground="#c0392b")
        self.bet_text.pack(fill=tk.X)
        self.bet_text.insert(tk.END, "")
        self.bet_text.config(state=tk.DISABLED)

        # 保存区
        save_frame = ttk.LabelFrame(main_frame, text="保存剩余号码与统计", padding=8)
        save_frame.pack(fill=tk.X, pady=(8, 0))

        save_row1 = ttk.Frame(save_frame)
        save_row1.pack(fill=tk.X)

        ttk.Label(save_row1, text="期号：").pack(side=tk.LEFT, padx=(5, 2), pady=5)
        self.save_issue_var = tk.StringVar()
        ttk.Entry(save_row1, textvariable=self.save_issue_var, width=12).pack(side=tk.LEFT, padx=(2, 15), pady=5)

        tk.Button(save_row1, text="  💾 保存当前预测结果  ", bg="#5bc0de", fg="white",
                  relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                  command=self._save_remain_numbers).pack(side=tk.LEFT, padx=6, pady=5)

        tk.Button(save_row1, text="   预测对错统计  ", bg="#337ab7", fg="white",
                  relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                  command=self._calc_prediction_stats).pack(side=tk.LEFT, padx=6, pady=5)

        stats_frame = ttk.Frame(save_frame)
        stats_frame.pack(fill=tk.X, pady=(5, 0))

        self.stats_label = ttk.Label(stats_frame, text="点击\"预测对错统计\"按钮查看详细统计和记录")
        self.stats_label.pack(anchor=tk.W, padx=5)

        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground="blue")
        self.status_label.pack(fill=tk.X, pady=(5, 0))

        self._refresh_saved_list()
        self._set_default_issue()

    def _get_next_issue(self):
        history = self.history_manager.get_all()
        if not history:
            return ""
        history_sorted = sorted(history, key=lambda x: str(x["issue"]))
        latest_issue = str(history_sorted[-1]["issue"])
        try:
            year = int(latest_issue[:4])
            period_num = int(latest_issue[4:])
            next_period = period_num + 1
            if next_period > 999:
                next_period = 1
                year += 1
            return f"{year}{next_period:03d}"
        except Exception:
            return ""

    def _set_default_issue(self):
        if self.prediction_data and "params" in self.prediction_data:
            ni = self.prediction_data["params"].get("next_issue", "")
            if ni:
                self.save_issue_var.set(ni)
                return
        ni = self._get_next_issue()
        if ni:
            self.save_issue_var.set(ni)

    def _generate_one_predictor(self, pid, num_count):
        return {
            "predictor_id": pid + 1,
            "numbers": random.sample(NUM_ALL, min(num_count, 80))
        }

    def _generate_predictions(self):
        try:
            predictor_count = int(self.predictor_count_var.get())
            num_count = int(self.num_count_var.get())
            predict_periods = int(self.predict_periods_var.get())

            if predictor_count <= 0 or predict_periods <= 0:
                messagebox.showerror("错误", "预测者数量和预测期数必须大于0")
                return
            if num_count <= 0:
                messagebox.showerror("错误", "每预测者号码数量必须大于0")
                return
            if num_count > 80:
                messagebox.showerror("错误", "每预测者号码数量不能超过80")
                return

            history = self.history_manager.get_all()
            history.sort(key=lambda x: str(x["issue"]))
            recent_history = history[-predict_periods:] if len(history) > predict_periods else history

            if not recent_history:
                messagebox.showerror("错误", "历史数据为空，请先在历史查询中添加开奖记录")
                return

            latest_issue = str(recent_history[-1]["issue"])
            year = int(latest_issue[:4])
            period_num = int(latest_issue[4:])
            next_period = period_num + 1
            if next_period > 999:
                next_period = 1
                year += 1
            next_issue = f"{year}{next_period:03d}"

            total = predict_periods + 1

            def do_gen():
                predictions = {}
                for i, record in enumerate(recent_history):
                    issue = str(record["issue"])
                    result_num = record["number"]
                    predictions[issue] = {
                        "result": result_num,
                        "predictors": []
                    }
                    for pid in range(predictor_count):
                        predictions[issue]["predictors"].append(self._generate_one_predictor(pid, num_count))

                    if (i + 1) % 5 == 0 or i == len(recent_history) - 1:
                        self.root.after(0, lambda p=i + 1, t=total: self.status_var.set(f"正在生成预测数据... {p}/{t}"))

                predictions[next_issue] = {"result": "", "predictors": []}
                for pid in range(predictor_count):
                    predictions[next_issue]["predictors"].append(self._generate_one_predictor(pid, num_count))

                self.prediction_data = {
                    "params": {
                        "predictor_count": predictor_count,
                        "num_count": num_count,
                        "min_streak": int(self.min_streak_var.get()),
                        "predict_periods": predict_periods,
                        "next_issue": next_issue
                    },
                    "predictions": predictions
                }

                self._save_prediction_data()
                self.root.after(0, lambda: messagebox.showinfo(
                    "成功", f"已生成{predictor_count}个预测者，{len(recent_history)}期历史预测 + 1期新预测（{next_issue}）"))
                self.root.after(0, lambda: self.status_var.set(f"已生成 {total} 期预测数据"))
                self.root.after(0, self._set_default_issue)

            self.status_var.set(f"正在生成预测数据... 0/{total}")
            threading.Thread(target=do_gen, daemon=True).start()

        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")

    def _add_predictions(self):
        if not self.prediction_data or "predictions" not in self.prediction_data:
            messagebox.showerror("错误", "请先生成预测数据后再补齐")
            return

        history = self.history_manager.get_all()
        if not history:
            messagebox.showerror("错误", "历史数据为空")
            return

        predictions = self.prediction_data["predictions"]
        history_sorted = sorted(history, key=lambda x: str(x["issue"]))
        history_issues = [str(h["issue"]) for h in history_sorted]
        history_map = {str(h["issue"]): h["number"] for h in history_sorted}
        predicted_issues_set = set(predictions.keys())

        max_history_issue = history_issues[-1]
        max_history_year = int(max_history_issue[:4])
        max_history_num = int(max_history_issue[4:])

        max_pred_issue = max(predicted_issues_set)
        max_pred_year = int(max_pred_issue[:4])
        max_pred_num = int(max_pred_issue[4:])

        all_issues = []
        cur_year, cur_num = max_pred_year, max_pred_num
        while True:
            issue = f"{cur_year}{cur_num:03d}"
            if cur_year > max_history_year or (cur_year == max_history_year and cur_num > max_history_num):
                break
            if cur_year == max_pred_year and cur_num == max_pred_num:
                cur_num += 1
                if cur_num > 999:
                    cur_num = 1
                    cur_year += 1
                continue
            all_issues.append(issue)
            cur_num += 1
            if cur_num > 999:
                cur_num = 1
                cur_year += 1

        missing_issues = all_issues
        next_year, next_num = max_history_year, max_history_num + 1
        if next_num > 999:
            next_num = 1
            next_year += 1
        next_issue_new = f"{next_year}{next_num:03d}"
        need_add_next = next_issue_new not in predicted_issues_set

        if not missing_issues and not need_add_next:
            messagebox.showinfo("提示", "所有历史期号和新一期都已预测，无需补齐")
            return

        params = self.prediction_data.get("params", {})
        predictor_count = params.get("predictor_count", 0)
        num_count = params.get("num_count", 10)

        total_issues = len(missing_issues) + (1 if need_add_next else 0)
        current_progress = 0

        def do_add():
            nonlocal current_progress
            try:
                added_count = 0

                def gen_predictors(issue_name):
                    new_preds = []
                    for pid in range(predictor_count):
                        new_preds.append(self._generate_one_predictor(pid, num_count))
                        if (pid + 1) % 500 == 0:
                            pi = int((pid + 1) / predictor_count * 100)
                            self.root.after(0, lambda p=current_progress, t=total_issues, i=issue_name, x=pi:
                                            self.status_var.set(f"正在补齐预测... {p}/{t} ({i}: {x}%)"))
                    return new_preds

                for issue in missing_issues:
                    predictions[issue] = {
                        "result": history_map.get(issue, ""),
                        "predictors": gen_predictors(issue)
                    }
                    added_count += 1
                    current_progress += 1
                    if current_progress % 5 == 0 or current_progress == total_issues:
                        self.root.after(0, lambda p=current_progress, t=total_issues:
                                        self.status_var.set(f"正在补齐预测... {p}/{t}"))

                if need_add_next:
                    predictions[next_issue_new] = {"result": "", "predictors": gen_predictors(next_issue_new)}
                    added_count += 1
                    current_progress += 1
                    self.root.after(0, lambda p=current_progress, t=total_issues:
                                    self.status_var.set(f"正在补齐预测... {p}/{t}"))
                    self.prediction_data["params"]["next_issue"] = next_issue_new

                self._save_prediction_data()
                msg = f"已补齐 {added_count} 期预测数据"
                if need_add_next:
                    msg += f"（含新一期 {next_issue_new}）"
                self.root.after(0, lambda m=msg: messagebox.showinfo("成功", m))
                self.root.after(0, lambda: self.status_var.set(f"已补齐 {added_count} 期"))
                self.root.after(0, self._refresh_saved_list)
                self.root.after(0, self._set_default_issue)
            except Exception as e:
                self.root.after(0, lambda err=str(e): messagebox.showerror("补齐预测错误", f"错误信息：{err}"))
                self.root.after(0, lambda: self.status_var.set("补齐预测失败"))

        self.status_var.set(f"正在补齐预测... 0/{total_issues}")
        threading.Thread(target=do_add, daemon=True).start()

    def _query_predictor_data(self):
        if not self.prediction_data or "predictions" not in self.prediction_data:
            messagebox.showerror("错误", "请先生成预测数据")
            return

        if self._is_legacy_data():
            messagebox.showerror(
                "数据结构不兼容",
                "检测到旧版预测数据结构（DLT的front/back），请先点击\"应用参数并生成预测数据\"重新生成。"
            )
            return

        try:
            pid = int(self.query_pid_var.get()) - 1
        except ValueError:
            messagebox.showerror("错误", "请输入有效的预测者ID")
            return

        params = self.prediction_data.get("params", {})
        predictor_count = params.get("predictor_count", 0)
        if pid < 0 or pid >= predictor_count:
            messagebox.showerror("错误", f"预测者ID必须在1-{predictor_count}之间")
            return

        predictions = self.prediction_data["predictions"]
        issues = sorted(predictions.keys(), reverse=True)

        for item in self.query_tree.get_children():
            self.query_tree.delete(item)

        for issue in issues:
            pred_data = predictions[issue]
            result_str = pred_data.get("result", "")
            predictors = pred_data["predictors"]
            if pid >= len(predictors):
                continue
            pred = predictors[pid]
            nums = pred.get("numbers", [])

            if result_str:
                drawn = _parse_result(result_str)
                drawn_set = set(drawn)
                # 命中 = 预测号码全部在20个开奖号中
                hit = all(n in drawn_set for n in nums) if nums else False
                hit_str = "对" if hit else "错"
                tags = ("hit_row",) if hit else ()
                display_result = " ".join(f"{n:02d}" for n in drawn)
            else:
                hit_str = ""
                tags = ("pending",)
                display_result = "待开奖"

            self.query_tree.insert("", tk.END, values=(
                issue, display_result,
                " ".join(f"{n:02d}" for n in nums),
                hit_str
            ), tags=tags)

    def _refresh_results(self):
        if not self.saved_predictions:
            messagebox.showinfo("提示", "暂无保存的预测记录")
            return

        # 先回填旧记录缺失的 remain_hit / bet_hit / bet_prize 字段
        backfill_changed = self._backfill_all_records()

        history = self.history_manager.get_all()
        history_map = {str(h["issue"]): h["number"] for h in history}

        updated_count = 0
        for rec in self.saved_predictions:
            issue = rec["issue"]
            old_result = rec.get("result", "")
            new_result = history_map.get(issue, "")

            remain = rec.get("remain", [])
            bet = rec.get("bet", [])

            if not new_result:
                if old_result:
                    rec["result"] = ""
                    rec["hit"] = False
                    rec["remain_hit"] = 0
                    rec["bet_hit"] = 0
                    rec["bet_prize"] = "无奖"
                    updated_count += 1
            elif old_result != new_result:
                rec["result"] = new_result
                drawn = _parse_result(new_result)
                # 剩余命中数 = 20个开奖号中落在剩余号码里的个数
                remain_set = set(remain)
                remain_hit = len(set(drawn) & remain_set) if drawn else 0
                rec["remain_hit"] = remain_hit
                # 杀号正确 = 所有20个开奖号都在剩余号码中
                rec["hit"] = (remain_hit == len(drawn)) if drawn else False
                # 选十命中数与奖级
                if bet and drawn:
                    bet_hit = len(set(drawn) & set(bet))
                    rec["bet_hit"] = bet_hit
                    rec["bet_prize"], _ = _xuanshi_prize(bet_hit)
                else:
                    rec["bet_hit"] = 0
                    rec["bet_prize"] = "无奖"
                updated_count += 1

        predictions_updated = 0
        if self.prediction_data and "predictions" in self.prediction_data:
            predictions = self.prediction_data["predictions"]
            for issue, pred_data in predictions.items():
                if pred_data.get("result", "") == "" and issue in history_map:
                    pred_data["result"] = history_map[issue]
                    predictions_updated += 1
            if predictions_updated > 0:
                self._save_prediction_data()

        if updated_count > 0 or backfill_changed:
            if updated_count > 0:
                self._save_saved_predictions()
            self._refresh_saved_list()
            msg_parts = []
            if updated_count > 0:
                msg_parts.append(f"已同步 {updated_count} 条开奖结果（预测数据同步 {predictions_updated} 条）")
            if backfill_changed:
                msg_parts.append("已补算旧记录缺失的剩余命中/选十命中字段")
            messagebox.showinfo("成功", "；".join(msg_parts))
        else:
            messagebox.showinfo("提示", "数据已是最新，无需更新")

    def _backfill_record_fields(self, rec):
        """为单条已开奖记录补算缺失的 remain_hit / hit / bet_hit / bet_prize 字段。
        返回是否有字段被补算（用于决定是否需要持久化）。"""
        result = rec.get("result", "")
        if not result:
            return False
        drawn = _parse_result(result)
        if not drawn:
            return False
        changed = False
        remain = rec.get("remain", [])
        remain_set = set(remain)
        drawn_set = set(drawn)

        # remain_hit：20个开奖号中落在剩余号码里的个数
        if "remain_hit" not in rec:
            rec["remain_hit"] = len(drawn_set & remain_set)
            changed = True
        # hit：杀号正确 = 所有开奖号都在剩余号码中
        if "hit" not in rec:
            rec["hit"] = (rec["remain_hit"] == len(drawn))
            changed = True
        # bet_hit / bet_prize：选十命中数与奖级
        bet = rec.get("bet", [])
        if bet and "bet_hit" not in rec:
            rec["bet_hit"] = len(drawn_set & set(bet))
            rec["bet_prize"], _ = _xuanshi_prize(rec["bet_hit"])
            changed = True
        return changed

    def _backfill_all_records(self):
        """扫描全部已保存记录，补算缺失字段；若有变更则持久化。返回是否发生变更。"""
        changed = False
        for rec in self.saved_predictions:
            if self._backfill_record_fields(rec):
                changed = True
        if changed:
            self._save_saved_predictions()
        return changed

    def _calc_prediction_stats(self):
        if not self.saved_predictions:
            messagebox.showinfo("提示", "暂无保存的预测记录")
            return

        # 回填旧记录缺失的 remain_hit / bet_hit / bet_prize 字段
        self._backfill_all_records()

        opened_recs = [r for r in self.saved_predictions if r.get("result")]
        total = len(opened_recs)
        if total == 0:
            messagebox.showinfo("提示", "暂无已开奖的预测记录")
            return

        # ===== 剩余号码策略统计（基于 remain） =====
        hit_count = sum(1 for r in opened_recs if r.get("hit", False))
        miss_count = total - hit_count
        hit_rate = f"{hit_count / total * 100:.1f}%"
        miss_rate = f"{miss_count / total * 100:.1f}%"
        remain_hits = [r.get("remain_hit", 0) for r in opened_recs]
        avg_remain = sum(remain_hits) / total if total else 0
        min_remain = min(remain_hits) if remain_hits else 0
        max_remain = max(remain_hits) if remain_hits else 0

        # ===== 选十码策略统计（基于 bet） =====
        prize_dist = {}     # 奖级描述 → 期数
        total_money = 0
        win_count = 0
        for r in opened_recs:
            prize = r.get("bet_prize", "无奖")
            prize_dist[prize] = prize_dist.get(prize, 0) + 1
            _, money = _xuanshi_prize(r.get("bet_hit", 0))
            total_money += money
            if prize != "无奖":
                win_count += 1
        win_rate = f"{win_count / total * 100:.1f}%" if total else "0.0%"

        stats_text = (f"已开奖 {total} 期 | "
                      f"杀号正确 {hit_count}/{total} ({hit_rate}) | "
                      f"选十中奖 {win_count}/{total} ({win_rate})")
        self.stats_label.config(text=stats_text)

        top = tk.Toplevel(self.parent)
        top.title("预测对错统计")
        top.geometry("1180x680")
        top.transient(self.parent)
        top.grab_set()

        # ===== 总览：剩余号码策略 =====
        remain_summary = ttk.LabelFrame(top, text="剩余号码策略统计（杀号：20个开奖号中落在剩余号码里的个数）", padding=10)
        remain_summary.pack(fill=tk.X, padx=10, pady=(10, 4))

        r_row1 = ttk.Frame(remain_summary)
        r_row1.pack(fill=tk.X, pady=2)
        ttk.Label(r_row1, text=f"总开奖期数：{total} 期", font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT, padx=10)
        ttk.Label(r_row1, text=f"杀号正确(20/20)：{hit_count} 期 ({hit_rate})", foreground="#d32f2f",
                  font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT, padx=10)
        ttk.Label(r_row1, text=f"杀号错误：{miss_count} 期 ({miss_rate})", foreground="#388e3c",
                  font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT, padx=10)

        r_row2 = ttk.Frame(remain_summary)
        r_row2.pack(fill=tk.X, pady=2)
        ttk.Label(r_row2, text=f"剩余命中：平均 {avg_remain:.1f}/20 | 最少 {min_remain} | 最多 {max_remain}",
                  foreground="#6a1b9a", font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT, padx=10)
        # 剩余命中分布（按命中数 0-20 计数）
        r_row3 = ttk.Frame(remain_summary)
        r_row3.pack(fill=tk.X, pady=2)
        ttk.Label(r_row3, text="命中分布：", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(10, 2))
        remain_dist = {}
        for h in remain_hits:
            remain_dist[h] = remain_dist.get(h, 0) + 1
        for h in sorted(remain_dist.keys()):
            cnt = remain_dist[h]
            color = "#d32f2f" if h == 20 else ("#f57c00" if h >= 18 else "#666666")
            ttk.Label(r_row3, text=f"{h}/20×{cnt}", foreground=color,
                      font=("微软雅黑", 9, "bold")).pack(side=tk.LEFT, padx=4)

        # ===== 总览：选十码策略 =====
        bet_summary = ttk.LabelFrame(top, text="选十码策略统计（10个选十码中落在20个开奖号里的个数 → 奖级）", padding=10)
        bet_summary.pack(fill=tk.X, padx=10, pady=(4, 4))

        b_row1 = ttk.Frame(bet_summary)
        b_row1.pack(fill=tk.X, pady=2)
        ttk.Label(b_row1, text=f"选十中奖：{win_count}/{total} 期 ({win_rate})", foreground="#1565c0",
                  font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT, padx=10)
        ttk.Label(b_row1, text=f"累计奖金：{total_money:,} 元", foreground="#f57c00",
                  font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT, padx=10)

        # 奖级分布
        b_row2 = ttk.Frame(bet_summary)
        b_row2.pack(fill=tk.X, pady=2)
        ttk.Label(b_row2, text="奖级分布：", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(10, 2))
        # 按命中数降序展示
        prize_order = []
        for h in [10, 9, 8, 7, 6, 5, 0]:
            name, _ = _xuanshi_prize(h)
            prize_order.append(name)
        for name in prize_order:
            cnt = prize_dist.get(name, 0)
            if cnt > 0:
                ttk.Label(b_row2, text=f"{name}×{cnt}", foreground="#6a1b9a",
                          font=("微软雅黑", 9, "bold")).pack(side=tk.LEFT, padx=6)
        if prize_dist.get("无奖", 0) > 0:
            ttk.Label(b_row2, text=f"无奖×{prize_dist['无奖']}", foreground="#999999",
                      font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6)

        # ===== 详细记录：剩余号码 + 选十码 并列 =====
        list_frame = ttk.LabelFrame(top, text="详细记录", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        columns = ("issue", "remain", "bet", "result", "rhit", "bhit", "prize")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        tree.heading("issue", text="期号")
        tree.heading("remain", text="剩余号码")
        tree.heading("bet", text="选十码")
        tree.heading("result", text="开奖号")
        tree.heading("rhit", text="剩余中")
        tree.heading("bhit", text="选十中")
        tree.heading("prize", text="奖级")
        tree.column("issue", width=85, anchor=tk.CENTER)
        tree.column("remain", width=240, anchor=tk.CENTER)
        tree.column("bet", width=140, anchor=tk.CENTER)
        tree.column("result", width=240, anchor=tk.CENTER)
        tree.column("rhit", width=60, anchor=tk.CENTER)
        tree.column("bhit", width=60, anchor=tk.CENTER)
        tree.column("prize", width=120, anchor=tk.CENTER)

        tree.tag_configure("prize_win", foreground="#d32f2f", font=("", 10, "bold"))
        tree.tag_configure("prize_none", foreground="#999999")
        tree.tag_configure("remain_ok", foreground="#1565c0", font=("", 10, "bold"))
        tree.tag_configure("pending", foreground="#bbbbbb")

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        for rec in reversed(self.saved_predictions):
            issue = rec.get("issue", "")
            remain = rec.get("remain", [])
            bet = rec.get("bet", [])
            result = rec.get("result", "")
            is_hit = rec.get("hit", False)
            remain_hit = rec.get("remain_hit", 0)
            bet_hit = rec.get("bet_hit", 0)
            prize = rec.get("bet_prize", "无奖")

            # 剩余号码显示：前缀标注个数，如 "(47个) 01 02 03 ..."
            if remain:
                remain_disp = f"({len(remain)}个) " + " ".join(f"{n:02d}" for n in remain)
            else:
                remain_disp = "-"

            if result:
                result_disp = " ".join(f"{n:02d}" for n in _parse_result(result))
                rhit_str = f"{remain_hit}/20"
                bhit_str = f"{bet_hit}/10"
                # 优先按选十中奖高亮，其次按杀号正确高亮
                if prize != "无奖":
                    tags = ("prize_win",)
                elif is_hit:
                    tags = ("remain_ok",)
                else:
                    tags = ("prize_none",)
            else:
                result_disp = "待开奖"
                rhit_str = ""
                bhit_str = ""
                prize = ""
                tags = ("pending",)

            tree.insert("", tk.END, values=(
                issue,
                remain_disp,
                " ".join(f"{n:02d}" for n in bet) if bet else "-",
                result_disp,
                rhit_str,
                bhit_str,
                prize
            ), tags=tags)


    def _calculate_kill_numbers(self):
        if not self.prediction_data or "predictions" not in self.prediction_data:
            messagebox.showerror("错误", "请先生成预测数据")
            return

        if self._is_legacy_data():
            messagebox.showerror(
                "数据结构不兼容",
                "检测到旧版预测数据结构（DLT的front/back），请先点击\"应用参数并生成预测数据\"重新生成。"
            )
            return

        try:
            min_streak = int(self.min_streak_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的连续命中期数")
            return

        if min_streak <= 0:
            messagebox.showerror("错误", "最小连续命中期数必须大于0")
            return

        predictions = self.prediction_data["predictions"]
        params = self.prediction_data.get("params", {})
        predictor_count = params.get("predictor_count", 0)
        num_count = params.get("num_count", 10)
        next_issue = params.get("next_issue", "")

        if not next_issue or next_issue not in predictions:
            messagebox.showerror("错误", "未找到下一期预测数据")
            return

        next_pred_data = predictions[next_issue]
        next_predictors = next_pred_data["predictors"]

        history_issues = sorted(
            [k for k in predictions.keys() if k != next_issue and predictions[k].get("result", "")],
            reverse=True
        )
        total_periods = len(history_issues)

        if total_periods == 0:
            messagebox.showerror("错误", "没有可用的历史预测数据用于计算")
            return

        def do_calc():
            # 预缓存每期开奖号码集合
            history_nums = {}
            for issue in history_issues:
                history_nums[issue] = set(_parse_result(predictions[issue]["result"]))

            issue_predictors = {issue: predictions[issue]["predictors"] for issue in history_issues}

            kill_details = []  # (pid, seq, kill_num, streak, hit_rate)
            kill_set = set()

            for pid in range(predictor_count):
                if pid >= len(next_predictors):
                    break
                next_pred = next_predictors[pid]
                next_nums = next_pred.get("numbers", [])

                # 每个序号 i 独立计算 streak
                for i in range(num_count):
                    if i >= len(next_nums):
                        break
                    kill_num = next_nums[i]

                    streak = 0
                    hit_count = 0
                    streak_active = True
                    for issue in history_issues:  # 已 reverse=True，从新到旧
                        predictors = issue_predictors[issue]
                        if pid >= len(predictors):
                            break
                        nums_list = predictors[pid].get("numbers", [])
                        if i >= len(nums_list):
                            break  # 该期该序号缺失，视为"错"，streak 中断
                        num = nums_list[i]
                        if num in history_nums[issue]:
                            hit_count += 1
                            if streak_active:
                                streak += 1
                        else:
                            streak_active = False

                    if streak >= min_streak:
                        kill_set.add(kill_num)
                        kill_details.append(
                            (pid + 1, i + 1, f"{kill_num:02d}", streak, f"{hit_count}/{total_periods}")
                        )

                if (pid + 1) % 500 == 0:
                    self.root.after(0, lambda p=pid + 1, t=predictor_count:
                                    self.status_var.set(f"正在计算杀号... {p}/{t}"))

            # 排序：streak 降序、pid 升序、seq 升序
            kill_details.sort(key=lambda x: (-x[3], x[0], x[1]))

            remain = sorted(set(NUM_ALL) - kill_set)
            # 选十码：在剩余号码范围内取预测者共识最高的10个
            bet = _compute_bet(next_predictors, remain)

            def update_ui():
                self.current_bet = bet
                for item in self.kill_tree.get_children():
                    self.kill_tree.delete(item)
                for detail in kill_details:
                    self.kill_tree.insert("", tk.END, values=detail)

                self.kill_label.config(
                    text=f"杀号对应预测期数：{total_periods}期历史 + {next_issue}期新预测 | "
                         f"杀号条目数：{len(kill_details)} | 去重后杀号数：{len(kill_set)}"
                )
                self.remain_label.config(text=f"剩余号码总数：{len(remain)}")
                self.remain_text.config(state=tk.NORMAL)
                self.remain_text.delete(1.0, tk.END)
                self.remain_text.insert(tk.END, " ".join(f"{n:02d}" for n in remain))
                self.remain_text.config(state=tk.DISABLED)

                self.bet_label.config(text=f"选十码（{len(bet)}个）：")
                self.bet_text.config(state=tk.NORMAL)
                self.bet_text.delete(1.0, tk.END)
                self.bet_text.insert(tk.END, " ".join(f"{n:02d}" for n in bet))
                self.bet_text.config(state=tk.DISABLED)

                self.status_var.set("杀号计算完成")
                messagebox.showinfo(
                    "成功",
                    f"杀号计算完成\n剩余号码：{len(remain)}个（1-80 去除 {len(kill_set)} 个杀号）\n"
                    f"选十码：{' '.join(f'{n:02d}' for n in bet)}"
                )

            self.root.after(0, update_ui)

        self.status_var.set(f"正在计算杀号... 0/{predictor_count}")
        threading.Thread(target=do_calc, daemon=True).start()

    def _save_remain_numbers(self):
        issue = self.save_issue_var.get().strip()
        if not issue:
            messagebox.showerror("错误", "请输入期号")
            return

        # 从当前 UI 读取剩余号码
        self.remain_text.config(state=tk.NORMAL)
        remain_str = self.remain_text.get(1.0, tk.END).strip()
        self.remain_text.config(state=tk.DISABLED)

        try:
            remain = [int(x) for x in remain_str.split()]
            if not all(1 <= n <= 80 for n in remain):
                raise ValueError
        except Exception:
            messagebox.showerror("错误", "剩余号码无效，请先点击\"计算杀号\"")
            return

        history = self.history_manager.get_all()
        history_map = {str(h["issue"]): h["number"] for h in history}
        result = history_map.get(issue, "")

        hit = False
        remain_hit = 0   # 20个开奖号中落在剩余号码里的个数 (0-20)
        if result:
            drawn = _parse_result(result)
            remain_set = set(remain)
            remain_hit = len(set(drawn) & remain_set) if drawn else 0
            # 命中 = 所有20个开奖号都在剩余号码中（即没有杀错号）
            hit = (remain_hit == len(drawn)) if drawn else False

        # 选十码：优先用当前计算的 current_bet，否则从预测数据重新推导
        bet = list(self.current_bet)
        if not bet and self.prediction_data and "predictions" in self.prediction_data:
            params = self.prediction_data.get("params", {})
            next_issue = params.get("next_issue", "")
            preds = self.prediction_data["predictions"]
            if next_issue and next_issue in preds:
                bet = _compute_bet(preds[next_issue].get("predictors", []), remain)

        # 选十命中数与奖级
        bet_hit = 0
        bet_prize = "无奖"
        if result and bet:
            drawn = _parse_result(result)
            bet_hit = len(set(drawn) & set(bet))
            bet_prize, _ = _xuanshi_prize(bet_hit)

        for rec in self.saved_predictions:
            if rec["issue"] == issue:
                messagebox.showwarning("提示", f"期号 {issue} 已存在，请勿重复保存")
                return

        new_record = {
            "issue": issue,
            "remain": remain,
            "bet": bet,
            "result": result,
            "hit": hit,
            "remain_hit": remain_hit,
            "bet_hit": bet_hit,
            "bet_prize": bet_prize
        }
        self.saved_predictions.append(new_record)
        self.saved_predictions.sort(key=lambda x: x["issue"])
        self._save_saved_predictions()
        self._refresh_saved_list()
        bet_info = f"\n选十码：{' '.join(f'{n:02d}' for n in bet)}" if bet else "\n选十码：无"
        if result:
            messagebox.showinfo("成功", f"期号 {issue} 的预测结果已保存\n剩余号码：{len(remain)}个{bet_info}\n剩余命中：{remain_hit}/20 | 选十命中：{bet_hit}/10 | 奖级：{bet_prize}")
        else:
            messagebox.showinfo("成功", f"期号 {issue} 的预测结果已保存\n剩余号码：{len(remain)}个{bet_info}\n（待开奖后刷新可查看中奖情况）")
