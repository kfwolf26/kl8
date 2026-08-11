import tkinter as tk
from tkinter import ttk, scrolledtext
from tkinter.messagebox import showwarning, showinfo
import itertools
import random
from math import comb


# ===== 福彩快乐8规则常量 =====
# 号码池 1-80，每期开奖20个号码；玩家选十（选10个号码）
NUM_RANGE = list(range(1, 81))   # 1-80
PICK_COUNT = 10

# 10个号码的奇偶比 / 大小比（奇:偶 / 小:大）
ODD_EVEN_OPTS = [f"{i}:{10 - i}" for i in range(10, -1, -1)]   # 10:0 ~ 0:10
BIG_SMALL_OPTS = [f"{i}:{10 - i}" for i in range(10, -1, -1)]  # 小:大

# 四区：1区(1-20) 2区(21-40) 3区(41-60) 4区(61-80)，共10个号码
ZONE_DEFS = [(1, 20), (21, 40), (41, 60), (61, 80)]
# 每区出现次数可选 0-10
ZONE_COUNT_OPTS = list(range(0, 11))

# 和值范围：最小 1+2+...+10=55，最大 71+72+...+80=755
SUM_MIN, SUM_MAX = 55, 755
# 跨度范围：最小 10连号=9，最大 80-1=79
SPAN_MIN, SPAN_MAX = 9, 79

# 候选生成策略
ENUM_THRESHOLD = 5_000_000   # 全组合数 ≤ 此值时穷举，否则随机采样
SAMPLE_SIZE = 500_000        # 随机采样注数
DISPLAY_LIMIT = 5000         # 结果显示上限


class FilterTool:
    def __init__(self, parent):
        self.parent = parent
        self.filter_vars = self._init_filter_vars()

        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_pane, width=600)
        main_pane.add(left_frame, weight=1)
        left_canvas = tk.Canvas(left_frame, bg="white")
        left_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=left_canvas.yview)
        self.filter_content = tk.Frame(left_canvas, bg="white")
        self.filter_content.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=self.filter_content, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        right_frame = ttk.Frame(main_pane, width=600)
        main_pane.add(right_frame, weight=1)
        ttk.Label(right_frame, text="过滤结果", font=("Arial", 12, "bold")).pack(pady=5)
        self.result_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        self.start_btn = tk.Button(btn_frame, text="  🚀 开始过滤  ", bg="#5cb85c", fg="white",
                                   relief=tk.RAISED, padx=5, pady=4, font=("微软雅黑", 9, "bold"),
                                   command=self.start_filter)
        self.start_btn.pack(side=tk.LEFT, padx=6)
        self.clear_btn = tk.Button(btn_frame, text="  🗑 清空条件  ", bg="#f0ad4e", fg="white",
                                   relief=tk.RAISED, padx=5, pady=4, font=("微软雅黑", 9),
                                   command=self.clear_all)
        self.clear_btn.pack(side=tk.LEFT, padx=6)
        self.help_btn = tk.Button(btn_frame, text="  💡 使用说明  ", bg="#5bc0de", fg="white",
                                   relief=tk.RAISED, padx=5, pady=4, font=("微软雅黑", 9),
                                   command=self.show_help)
        self.help_btn.pack(side=tk.RIGHT, padx=6)

        self._build_filter_ui()

    def _init_filter_vars(self):
        v = {}

        # 1. 杀号（1-80）
        v["kill"] = [tk.BooleanVar() for _ in range(80)]

        # 2. 胆码（1-80，最多10个）
        v["dan"] = [tk.BooleanVar() for _ in range(80)]

        # 3. 和值范围
        v["sum_min"] = tk.StringVar()
        v["sum_max"] = tk.StringVar()

        # 4. 跨度范围
        v["span_min"] = tk.StringVar()
        v["span_max"] = tk.StringVar()

        # 5. 奇偶比
        v["oe_mode"] = tk.IntVar(value=1)
        v["oe"] = [tk.BooleanVar() for _ in ODD_EVEN_OPTS]

        # 6. 大小比
        v["bs_mode"] = tk.IntVar(value=1)
        v["bs"] = [tk.BooleanVar() for _ in BIG_SMALL_OPTS]

        # 7. 四区比（每区允许的出现次数集合）
        v["zone"] = [[tk.BooleanVar() for _ in ZONE_COUNT_OPTS] for _ in ZONE_DEFS]

        # 8. 连号
        v["consec_mode"] = tk.IntVar(value=0)  # 0不过滤 1必无 2必有任意 3必有2连 4必有3连+

        # 9. 号码组（最多5组）
        v["number_group"] = []
        for _ in range(5):
            v["number_group"].append({
                "nums": [tk.BooleanVar() for _ in range(80)],
                "count": tk.StringVar(value="0")
            })

        return v

    def _build_filter_ui(self):
        # 1. 杀号
        self._add_section_title("1. 杀号（勾选需要排除的号码1-80，组合中不出现这些号码）")
        self._add_num_checkgroup(self.filter_content, self.filter_vars["kill"])

        # 2. 胆码
        self._add_section_title("2. 胆码（勾选必含的号码，最多10个；胆码越多搜索空间越小）")
        self._add_num_checkgroup(self.filter_content, self.filter_vars["dan"])

        # 3. 和值
        self._add_section_title(f"3. 和值过滤（{SUM_MIN}-{SUM_MAX}，10个号码之和；留空=不限制）")
        self._add_range_entry(self.filter_content, self.filter_vars["sum_min"], self.filter_vars["sum_max"])

        # 4. 跨度
        self._add_section_title(f"4. 跨度过滤（{SPAN_MIN}-{SPAN_MAX}，最大号码-最小号码；留空=不限制）")
        self._add_range_entry(self.filter_content, self.filter_vars["span_min"], self.filter_vars["span_max"])

        # 5. 奇偶比
        self._add_section_title("5. 奇偶比过滤（奇:偶，10个号码的奇偶比）")
        self._add_mode_checkgroup(self.filter_content, self.filter_vars["oe_mode"],
                                  self.filter_vars["oe"], ODD_EVEN_OPTS, cols=11)

        # 6. 大小比
        self._add_section_title("6. 大小比过滤（小:大，小=1-40，大=41-80）")
        self._add_mode_checkgroup(self.filter_content, self.filter_vars["bs_mode"],
                                  self.filter_vars["bs"], BIG_SMALL_OPTS, cols=11)

        # 7. 四区比
        self._add_section_title("7. 四区比过滤（1区1-20 / 2区21-40 / 3区41-60 / 4区61-80；勾选每区允许的出现次数，不勾选=不限制该区）")
        self._add_zone_selector(self.filter_content, self.filter_vars["zone"])

        # 8. 连号
        self._add_section_title("8. 连号过滤")
        consec_frame = ttk.Frame(self.filter_content)
        consec_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Radiobutton(consec_frame, text="不过滤", variable=self.filter_vars["consec_mode"], value=0).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(consec_frame, text="必须无连号", variable=self.filter_vars["consec_mode"], value=1).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(consec_frame, text="必有任意连号", variable=self.filter_vars["consec_mode"], value=2).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(consec_frame, text="必有2连", variable=self.filter_vars["consec_mode"], value=3).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(consec_frame, text="必有3连+", variable=self.filter_vars["consec_mode"], value=4).pack(side=tk.LEFT, padx=5)

        # 9. 号码组
        self._add_section_title("9. 号码组过滤（最多5组，勾选号码+指定出现次数0-10）")
        for i in range(5):
            group_frame = tk.Frame(self.filter_content, relief=tk.RAISED, borderwidth=1, bg="white")
            group_frame.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(group_frame, text=f"第{i + 1}组：", bg="white").pack(side=tk.LEFT, padx=5)
            num_frame = tk.Frame(group_frame, bg="white")
            num_frame.pack(side=tk.LEFT, padx=5)
            for j in range(80):
                r = j // 20
                c = j % 20
                tk.Checkbutton(num_frame, variable=self.filter_vars["number_group"][i]["nums"][j],
                               text=f"{j + 1:02d}", bg="white").grid(row=r, column=c, padx=1)
            tk.Label(group_frame, text="出现次数：", bg="white").pack(side=tk.LEFT, padx=5)
            ttk.Entry(group_frame, textvariable=self.filter_vars["number_group"][i]["count"], width=5).pack(side=tk.LEFT)
            tk.Label(group_frame, text="（0-10）", bg="white").pack(side=tk.LEFT)

    def _add_section_title(self, text):
        tk.Label(self.filter_content, text=text, font=("Arial", 10, "bold"),
                 fg="#2c3e50", bg="white").pack(anchor="w", padx=10, pady=(10, 5))

    def _add_num_checkgroup(self, parent, var_list):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=5)
        item_frame = tk.Frame(frame, bg="white")
        item_frame.pack(side=tk.TOP, padx=5, pady=5)
        for i, var in enumerate(var_list):
            r = i // 20
            c = i % 20
            tk.Checkbutton(item_frame, variable=var, text=f"{i + 1:02d}", bg="white").grid(row=r, column=c, padx=2, pady=2)
        btn_frame = tk.Frame(frame)
        btn_frame.pack(side=tk.TOP, padx=5)
        ttk.Button(btn_frame, text="全选", command=lambda: self._check_all(var_list, True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: self._check_all(var_list, False)).pack(side=tk.LEFT, padx=5)

    def _add_range_entry(self, parent, min_var, max_var):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(frame, text="最小值：").pack(side=tk.LEFT, padx=5)
        ttk.Entry(frame, textvariable=min_var, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(frame, text="最大值：").pack(side=tk.LEFT, padx=5)
        ttk.Entry(frame, textvariable=max_var, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(frame, text="（范围两端均可留空）", foreground="gray").pack(side=tk.LEFT, padx=5)

    def _add_mode_checkgroup(self, parent, mode_var, var_list, item_list, cols=10):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=5)
        mode_frame = tk.Frame(frame)
        mode_frame.pack(side=tk.TOP, padx=5)
        ttk.Radiobutton(mode_frame, text="排除选中", variable=mode_var, value=0).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="包含选中", variable=mode_var, value=1).pack(side=tk.LEFT, padx=5)
        item_frame = tk.Frame(frame, bg="white")
        item_frame.pack(side=tk.TOP, padx=5, pady=5)
        for idx, (item, var) in enumerate(zip(item_list, var_list)):
            r = idx // cols
            c = idx % cols
            tk.Checkbutton(item_frame, variable=var, text=str(item), bg="white").grid(row=r, column=c, padx=2, pady=2)
        btn_frame = tk.Frame(frame)
        btn_frame.pack(side=tk.TOP, padx=5)
        ttk.Button(btn_frame, text="全选", command=lambda: self._check_all(var_list, True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: self._check_all(var_list, False)).pack(side=tk.LEFT, padx=5)

    def _add_zone_selector(self, parent, zone_vars):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=5)
        for zi, (lo, hi) in enumerate(ZONE_DEFS):
            row = tk.Frame(frame, bg="white")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"{zi + 1}区({lo:02d}-{hi:02d})：", bg="white", width=14).pack(side=tk.LEFT)
            cnt_frame = tk.Frame(row, bg="white")
            cnt_frame.pack(side=tk.LEFT)
            for ci, cvar in enumerate(zone_vars[zi]):
                tk.Checkbutton(cnt_frame, variable=cvar, text=str(ci), bg="white").pack(side=tk.LEFT, padx=1)

    def _check_all(self, var_list, state):
        for var in var_list:
            var.set(state)

    def _parse_filters(self):
        f = {}

        # 1. 杀号
        f["kill"] = {i + 1 for i, var in enumerate(self.filter_vars["kill"]) if var.get()}

        # 2. 胆码
        f["dan"] = {i + 1 for i, var in enumerate(self.filter_vars["dan"]) if var.get()}

        # 3. 和值范围
        f["sum_min"] = self._parse_int_opt(self.filter_vars["sum_min"].get(), SUM_MIN, SUM_MAX)
        f["sum_max"] = self._parse_int_opt(self.filter_vars["sum_max"].get(), SUM_MIN, SUM_MAX)

        # 4. 跨度范围
        f["span_min"] = self._parse_int_opt(self.filter_vars["span_min"].get(), SPAN_MIN, SPAN_MAX)
        f["span_max"] = self._parse_int_opt(self.filter_vars["span_max"].get(), SPAN_MIN, SPAN_MAX)

        # 5. 奇偶比
        f["oe_mode"] = self.filter_vars["oe_mode"].get()
        f["oe"] = {ODD_EVEN_OPTS[i] for i, var in enumerate(self.filter_vars["oe"]) if var.get()}

        # 6. 大小比
        f["bs_mode"] = self.filter_vars["bs_mode"].get()
        f["bs"] = {BIG_SMALL_OPTS[i] for i, var in enumerate(self.filter_vars["bs"]) if var.get()}

        # 7. 四区比
        f["zone"] = []
        for zi in range(len(ZONE_DEFS)):
            allowed = {ci for ci, cvar in enumerate(self.filter_vars["zone"][zi]) if cvar.get()}
            f["zone"].append(allowed)

        # 8. 连号
        f["consec_mode"] = self.filter_vars["consec_mode"].get()

        # 9. 号码组
        f["number_group"] = []
        for group in self.filter_vars["number_group"]:
            nums = {i + 1 for i, var in enumerate(group["nums"]) if var.get()}
            if not nums:
                continue
            cnt_str = group["count"].get().strip()
            cnt = int(cnt_str) if cnt_str.isdigit() and 0 <= int(cnt_str) <= 10 else 0
            f["number_group"].append((nums, cnt))

        return f

    def _parse_int_opt(self, text, default_lo, default_hi):
        text = text.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _calc_oe(self, combo):
        odd = sum(1 for n in combo if n % 2 == 1)
        return f"{odd}:{10 - odd}"

    def _calc_bs(self, combo):
        small = sum(1 for n in combo if n <= 40)
        return f"{small}:{10 - small}"

    def _calc_zones(self, combo):
        counts = []
        for lo, hi in ZONE_DEFS:
            counts.append(sum(1 for n in combo if lo <= n <= hi))
        return counts

    def _calc_consec(self, combo):
        runs = []
        run_len = 1
        for i in range(1, len(combo)):
            if combo[i] - combo[i - 1] == 1:
                run_len += 1
            else:
                if run_len >= 2:
                    runs.append(run_len)
                run_len = 1
        if run_len >= 2:
            runs.append(run_len)
        return runs

    def _combo_pass(self, combo, f):
        """combo: 10个号码的有序列表。检查是否满足所有过滤条件。"""
        combo_set = set(combo)

        # 1. 和值
        if f["sum_min"] is not None or f["sum_max"] is not None:
            s = sum(combo)
            if f["sum_min"] is not None and s < f["sum_min"]:
                return False
            if f["sum_max"] is not None and s > f["sum_max"]:
                return False

        # 2. 跨度
        if f["span_min"] is not None or f["span_max"] is not None:
            sp = combo[-1] - combo[0]
            if f["span_min"] is not None and sp < f["span_min"]:
                return False
            if f["span_max"] is not None and sp > f["span_max"]:
                return False

        # 3. 奇偶比
        if f["oe"]:
            oe = self._calc_oe(combo)
            if f["oe_mode"] == 1 and oe not in f["oe"]:
                return False
            if f["oe_mode"] == 0 and oe in f["oe"]:
                return False

        # 4. 大小比
        if f["bs"]:
            bs = self._calc_bs(combo)
            if f["bs_mode"] == 1 and bs not in f["bs"]:
                return False
            if f["bs_mode"] == 0 and bs in f["bs"]:
                return False

        # 5. 四区比
        zone_counts = self._calc_zones(combo)
        for zi, allowed in enumerate(f["zone"]):
            if allowed and zone_counts[zi] not in allowed:
                return False

        # 6. 连号
        if f["consec_mode"] != 0:
            runs = self._calc_consec(combo)
            if f["consec_mode"] == 1:  # 必须无连号
                if runs:
                    return False
            elif f["consec_mode"] == 2:  # 必有任意连号
                if not runs:
                    return False
            elif f["consec_mode"] == 3:  # 必有2连（最长连=2）
                if not runs or max(runs) != 2:
                    return False
            elif f["consec_mode"] == 4:  # 必有3连+
                if not runs or max(runs) < 3:
                    return False

        # 7. 号码组
        for nums, cnt in f["number_group"]:
            actual = len(combo_set & nums)
            if actual != cnt:
                return False

        return True

    def _generate_candidates(self, dan_list, pool, need, f):
        """生成候选10码组合。返回 (candidates, mode_desc, space_size)。"""
        space_size = comb(len(pool), need) if need >= 0 else 0

        if need == 0:
            # 胆码正好10个，只有一种组合
            full = sorted(dan_list)
            candidates = [full] if self._combo_pass(full, f) else []
            return candidates, "胆码已满10个（唯一组合）", 1

        if space_size <= ENUM_THRESHOLD:
            # 穷举
            candidates = []
            for combo in itertools.combinations(pool, need):
                full = sorted(dan_list + list(combo))
                if self._combo_pass(full, f):
                    candidates.append(full)
            return candidates, f"穷举全组合（{space_size:,}）", space_size
        else:
            # 随机采样
            candidates = []
            seen = set()
            attempts = 0
            max_attempts = SAMPLE_SIZE * 5
            pool_len = len(pool)
            while len(seen) < SAMPLE_SIZE and attempts < max_attempts:
                combo = tuple(sorted(random.sample(pool, need)))
                seen.add(combo)
                attempts += 1
            for combo in seen:
                full = sorted(dan_list + list(combo))
                if self._combo_pass(full, f):
                    candidates.append(full)
            return candidates, f"随机采样（全组合{space_size:,}，采样{len(seen):,}）", space_size

    def start_filter(self):
        self.result_text.delete(1.0, tk.END)
        try:
            f = self._parse_filters()

            # 胆码数量校验
            if len(f["dan"]) > PICK_COUNT:
                showwarning("提示", f"胆码不能超过{PICK_COUNT}个")
                return
            if f["dan"] & f["kill"]:
                showwarning("提示", "胆码和杀号不能重叠")
                return

            dan_list = sorted(f["dan"])
            # 候选池：1-80 去掉杀号和胆码
            pool = [n for n in range(1, 81) if n not in f["kill"] and n not in f["dan"]]
            need = PICK_COUNT - len(dan_list)

            if need < 0:
                showwarning("提示", f"胆码不能超过{PICK_COUNT}个")
                return
            if len(pool) < need:
                showwarning("提示", "可用号码不足，请减少杀号或胆码")
                return

            self._log(f"玩法：福彩快乐8 选十（1-80选{PICK_COUNT}）")
            self._log(f"胆码：{dan_list if dan_list else '无'}（{len(dan_list)}个）")
            self._log(f"杀号：{sorted(f['kill']) if f['kill'] else '无'}（{len(f['kill'])}个）")
            self._log(f"待补号码：{need}个 / 候选池：{len(pool)}个号码")
            self._log("")

            self._log("正在生成并过滤候选组合...")
            self.result_text.update()

            candidates, mode_desc, space_size = self._generate_candidates(dan_list, pool, need, f)
            self._log(f"生成方式：{mode_desc}")
            self._log(f"过滤后剩余：{len(candidates):,} 注")

            total = len(candidates)
            if total == 0:
                self._log("\n暂无符合所有条件的号码！")
            else:
                self._log("\n" + "=" * 70)
                if total <= DISPLAY_LIMIT:
                    for full in candidates:
                        self._log(" ".join(f"{n:02d}" for n in full))
                    self._log(f"\n共输出 {total:,} 注")
                else:
                    self._log(f"（数量过多（{total:,} 注），仅显示前 {DISPLAY_LIMIT:,} 注示例）")
                    for full in candidates[:DISPLAY_LIMIT]:
                        self._log(" ".join(f"{n:02d}" for n in full))

            self._log("\n" + "=" * 70)
            self._log("过滤完成！（注：彩票开奖随机，本工具仅为号码筛选，不保证中奖）")

        except Exception as e:
            showwarning("错误", f"过滤过程中出现异常：{str(e)}")

    def _log(self, text):
        self.result_text.insert(tk.END, text + "\n")
        self.result_text.see(tk.END)

    def clear_all(self):
        for var in self.filter_vars["kill"]:
            var.set(False)
        for var in self.filter_vars["dan"]:
            var.set(False)

        for key in ["sum_min", "sum_max", "span_min", "span_max"]:
            self.filter_vars[key].set("")

        for key in ["oe", "bs"]:
            for var in self.filter_vars[key]:
                var.set(False)

        for zone in self.filter_vars["zone"]:
            for var in zone:
                var.set(False)

        for key in ["oe_mode", "bs_mode"]:
            self.filter_vars[key].set(1)
        self.filter_vars["consec_mode"].set(0)

        for group in self.filter_vars["number_group"]:
            for var in group["nums"]:
                var.set(False)
            group["count"].set("0")

        self.result_text.delete(1.0, tk.END)

    def show_help(self):
        help_text = """
福彩快乐8过滤工具使用说明：

【彩票规则】
- 号码池：1-80，每期开奖20个号码
- 选十玩法：从1-80中选10个不重复号码
- 选十中十：单注最高奖金500万元

【过滤条件】
1. 杀号：勾选需要排除的号码（组合中不出现这些号码）
2. 胆码：勾选必含的号码（最多10个）。胆码越多，搜索空间越小、速度越快
3. 和值：10个号码之和（范围55-755，留空=不限制）
4. 跨度：最大号码-最小号码（范围9-79，留空=不限制）
5. 奇偶比：10个号码的奇:偶比（如6:4表示6奇4偶）
6. 大小比：小(1-40):大(41-80)
7. 四区比：1区(1-20)/2区(21-40)/3区(41-60)/4区(61-80)，勾选每区允许的出现次数
8. 连号：5种模式（不过滤/必无/必有任意/必有2连/必有3连+）
9. 号码组：每组勾选号码并指定在10个号码中出现的精确次数（0-10）

【候选生成策略】
- 当全组合数 ≤ 500万 时：穷举所有组合并逐注过滤
- 当全组合数 > 500万 时：随机采样50万注再过滤（结果不完整但覆盖广）
- 增加胆码可大幅缩小搜索空间，建议选十至少设3-5个胆码

【模式说明】
- 包含选中：仅保留命中勾选项的组合
- 排除选中：排除命中勾选项的组合

【输出】
- 结果超过5000注时仅显示前5000注示例，但会显示总数
- 输出格式：01 05 12 18 25 30 33 40 44 51

注意事项：
- 选十全组合数约1.65万亿，必须借助胆码/杀号缩减或随机采样
- 彩票开奖为随机事件，本工具仅为号码筛选，不保证中奖
        """
        showinfo("使用说明", help_text)
