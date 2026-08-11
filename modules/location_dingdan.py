import tkinter as tk
from tkinter import ttk
import random
from utils.history_manager import HistoryManager

PREDICTOR_NAMES = [
    "神算子", "好运来", "金手指", "财源广", "福星照",
    "财运通", "吉祥星", "如意宝", "聚宝盆", "鸿运达"
]

NUM_MIN, NUM_MAX = 1, 80


# 各tab配置：tab_key -> (显示名, 选号个数, 模式: 'dan'=命中即在开奖号中, 'kill'=杀对即不在开奖号中)
TAB_CONFIG = [
    ("dan3", "定三胆", 3, "dan"),
    ("dan5", "定五胆", 5, "dan"),
    ("kill3", "杀三码", 3, "kill"),
    ("kill5", "杀五码", 5, "kill"),
]


def _parse_result(result_str):
    """解析 'n1,n2,...,n20' → list[int]。"""
    if not result_str:
        return []
    try:
        return [int(x) for x in result_str.split(",")]
    except Exception:
        return []


class LocationDingDan:
    def __init__(self, parent):
        self.parent = parent
        self.history_manager = HistoryManager()
        self.predictors = {}
        self.canvas_frames = {}
        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        for tab_key, tab_name, pick_count, mode in TAB_CONFIG:
            tab_frame = ttk.Frame(self.notebook)
            self.notebook.add(tab_frame, text=f"  {tab_name}  ")
            self._build_sub_tab(tab_frame, tab_key, pick_count, mode)

    def _build_sub_tab(self, parent, tab_key, pick_count, mode):
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(control_frame, text="统计期数：").pack(side=tk.LEFT, padx=(0, 5))
        period_var = tk.StringVar(value="25")
        ttk.Entry(control_frame, textvariable=period_var, width=8).pack(side=tk.LEFT, padx=(0, 10))

        hint = "命中=号码在20个开奖号中" if mode == "dan" else "杀对=号码不在20个开奖号中"
        ttk.Label(control_frame, text=f"（每预测者出{pick_count}个号码，{hint}）",
                  foreground="gray").pack(side=tk.LEFT, padx=5)

        self.predictors[tab_key] = {
            "period_var": period_var,
            "pick_count": pick_count,
            "mode": mode,
            "data": {}
        }

        tk.Button(control_frame, text="  🔄 刷新  ", bg="#5bc0de", fg="white",
                  relief=tk.RAISED, padx=5, pady=3, font=("微软雅黑", 9),
                  command=lambda k=tab_key: self._refresh_tab(k)).pack(side=tk.LEFT, padx=5)

        result_frame = ttk.LabelFrame(parent, text="预测结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        canvas = tk.Canvas(result_frame, bg="white")
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar_y = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

        scrollbar_x = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)

        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        table_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=table_frame, anchor=tk.NW)

        table_frame.bind("<Configure>", lambda e, c=canvas: self._on_frame_configure(c))

        self.canvas_frames[tab_key] = {
            "canvas": canvas,
            "table_frame": table_frame,
            "labels": []
        }

        self._refresh_tab(tab_key)

    def _on_frame_configure(self, canvas):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _get_next_issue(self):
        history = self.history_manager.get_all()
        if not history:
            return ""
        history.sort(key=lambda x: str(x["issue"]), reverse=True)
        latest_issue = str(history[0]["issue"])
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

    def _refresh_tab(self, tab_key):
        history = self.history_manager.get_all()
        if not history:
            self._clear_table(tab_key)
            return

        history.sort(key=lambda x: str(x["issue"]), reverse=False)

        try:
            periods = int(self.predictors[tab_key]["period_var"].get())
        except ValueError:
            periods = 25

        recent_history = history[-periods:] if len(history) > periods else history

        all_data = {}
        for record in recent_history:
            issue = str(record["issue"])
            result_num = record["number"]
            predictors_data = self._generate_predictors_for_period(tab_key, result_num)
            all_data[issue] = {
                "result": result_num,
                "predictors": predictors_data
            }

        next_issue = self._get_next_issue()
        if next_issue:
            all_data[next_issue] = {
                "result": "",
                "predictors": self._generate_predictors_for_period(tab_key, "")
            }

        self.predictors[tab_key]["data"] = all_data
        self._display_results(tab_key)

    def _generate_predictors_for_period(self, tab_key, result_str):
        """根据 tab 类型生成预测者的号码 + 命中情况。"""
        cfg = self.predictors[tab_key]
        pick_count = cfg["pick_count"]
        mode = cfg["mode"]
        predictors_data = []

        result_nums = _parse_result(result_str) if result_str else []
        result_set = set(result_nums)

        for i in range(len(PREDICTOR_NAMES)):
            name = PREDICTOR_NAMES[i]
            numbers = sorted(random.sample(range(NUM_MIN, NUM_MAX + 1), pick_count))

            hit_numbers = []
            if result_set:
                if mode == "dan":
                    # 命中 = 号码在20个开奖号中
                    hit_numbers = [n for n in numbers if n in result_set]
                elif mode == "kill":
                    # 杀对 = 号码不在20个开奖号中
                    hit_numbers = [n for n in numbers if n not in result_set]

            predictors_data.append({
                "name": name,
                "numbers": numbers,
                "hit_numbers": hit_numbers
            })

        return predictors_data

    def _display_results(self, tab_key):
        self._clear_table(tab_key)
        table_frame = self.canvas_frames[tab_key]["table_frame"]
        labels = []

        header_font = ("微软雅黑", 9, "bold")
        cell_font = ("微软雅黑", 9)
        cfg = self.predictors[tab_key]
        pick_count = cfg["pick_count"]

        row = 0
        ttk.Label(table_frame, text="期号", font=header_font, width=10, anchor=tk.CENTER).grid(row=row, column=0, padx=2, pady=2, sticky="nsew")
        ttk.Label(table_frame, text="开奖号", font=header_font, width=24, anchor=tk.CENTER).grid(row=row, column=1, padx=2, pady=2, sticky="nsew")

        col = 2
        for idx, name in enumerate(PREDICTOR_NAMES):
            ttk.Label(table_frame, text=name, font=header_font, width=pick_count * 5 + 2, anchor=tk.CENTER).grid(row=row, column=col, columnspan=pick_count, padx=2, pady=2, sticky="nsew")
            col += pick_count
            if idx < len(PREDICTOR_NAMES) - 1:
                sep = ttk.Separator(table_frame, orient='vertical')
                sep.grid(row=row, column=col, sticky='ns', padx=1)
                col += 1

        hit_label = "命中数" if cfg["mode"] == "dan" else "杀对数"
        ttk.Label(table_frame, text=hit_label, font=header_font, width=8, anchor=tk.CENTER).grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

        row += 1

        data = self.predictors[tab_key]["data"]
        for issue in sorted(data.keys()):
            record = data[issue]
            result_num = record["result"]
            is_next = result_num == ""

            if is_next:
                ttk.Label(table_frame, text=issue, font=("微软雅黑", 9, "bold"), width=10, anchor=tk.CENTER, foreground="#f57c00").grid(row=row, column=0, padx=2, pady=2, sticky="nsew")
                ttk.Label(table_frame, text="待开奖", font=("微软雅黑", 9, "bold"), width=24, anchor=tk.CENTER, foreground="#f57c00").grid(row=row, column=1, padx=2, pady=2, sticky="nsew")
            else:
                ttk.Label(table_frame, text=issue, font=cell_font, width=10, anchor=tk.CENTER).grid(row=row, column=0, padx=2, pady=2, sticky="nsew")
                # 开奖号20个，显示紧凑
                nums = _parse_result(result_num)
                disp = " ".join(f"{n:02d}" for n in nums) if nums else result_num
                ttk.Label(table_frame, text=disp, font=("Consolas", 8), width=24, anchor=tk.CENTER, foreground="#1976d2").grid(row=row, column=1, padx=2, pady=2, sticky="nsew")

            col = 2
            total_hits = 0
            for idx, pred in enumerate(record["predictors"]):
                numbers = pred["numbers"]
                hit_numbers = pred["hit_numbers"]

                for num in numbers:
                    if num in hit_numbers:
                        lbl = tk.Label(table_frame, text=f"{num:02d}", font=cell_font, width=5, anchor=tk.CENTER, foreground="#d32f2f")
                        total_hits += 1
                    else:
                        lbl = tk.Label(table_frame, text=f"{num:02d}", font=cell_font, width=5, anchor=tk.CENTER, foreground="#333333")
                    lbl.grid(row=row, column=col, padx=1, pady=2, sticky="nsew")
                    labels.append(lbl)
                    col += 1

                if idx < len(record["predictors"]) - 1:
                    sep = ttk.Separator(table_frame, orient='vertical')
                    sep.grid(row=row, column=col, sticky='ns', padx=1)
                    col += 1

            ttk.Label(table_frame, text=str(total_hits), font=cell_font, width=8, anchor=tk.CENTER).grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

            row += 1

        self.canvas_frames[tab_key]["labels"] = labels

        canvas = self.canvas_frames[tab_key]["canvas"]
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _clear_table(self, tab_key):
        table_frame = self.canvas_frames[tab_key]["table_frame"]
        for widget in table_frame.winfo_children():
            widget.destroy()
        self.canvas_frames[tab_key]["labels"] = []
