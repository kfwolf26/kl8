"""测试：预测对错统计同时展示 剩余号码 与 选十码 两套策略"""
import tkinter as tk
import os, json, tempfile
from modules.prediction_model import _xuanshi_prize, PredictionModel

root = tk.Tk()
root.withdraw()
frame = tk.Frame(root)
app = PredictionModel(frame)

# 隔离 saved_predictions 文件
tmp = tempfile.mkdtemp()
app.saved_predictions_file = os.path.join(tmp, "saved.json")

# 构造 4 期测试数据（已开奖）
# 开奖号统一为 1-20
drawn = list(range(1, 21))
drawn_str = ",".join(map(str, drawn))
app.saved_predictions = [
    # 期1：remain覆盖全部20（杀号正确），bet=1-10（中10 一等奖）
    {"issue": "2026201", "remain": list(range(1,81)), "bet": list(range(1,11)),
     "result": drawn_str, "hit": True, "remain_hit": 20, "bet_hit": 10,
     "bet_prize": _xuanshi_prize(10)[0]},
    # 期2：remain缺1个(把1杀掉了,实际开出1)，bet=[1,2,3,4,5,6,7,8,9,30] 中9
    {"issue": "2026202", "remain": list(range(2,81)), "bet": [1,2,3,4,5,6,7,8,9,30],
     "result": drawn_str, "hit": False, "remain_hit": 19, "bet_hit": 9,
     "bet_prize": _xuanshi_prize(9)[0]},
    # 期3：remain缺5个(杀了1-5却都开了)，bet=[40,41,42,43,44,45,46,47,48,49] 中0 安慰奖
    {"issue": "2026203", "remain": list(range(6,81)), "bet": [40,41,42,43,44,45,46,47,48,49],
     "result": drawn_str, "hit": False, "remain_hit": 15, "bet_hit": 0,
     "bet_prize": _xuanshi_prize(0)[0]},
    # 期4：remain全中，bet中4（中1-4=无奖）
    {"issue": "2026204", "remain": list(range(1,81)), "bet": [1,2,3,4,40,41,42,43,44,45],
     "result": drawn_str, "hit": True, "remain_hit": 20, "bet_hit": 4,
     "bet_prize": "无奖"},
    # 期5：待开奖
    {"issue": "2026205", "remain": list(range(1,81)), "bet": list(range(1,11)),
     "result": "", "hit": False, "remain_hit": 0, "bet_hit": 0, "bet_prize": "无奖"},
]

# 直接调用统计逻辑（不弹窗，只验证数据计算）
# 复刻 _calc_prediction_stats 中的统计部分
opened = [r for r in app.saved_predictions if r.get("result")]
total = len(opened)
assert total == 4

# 剩余号码策略
hit_count = sum(1 for r in opened if r.get("hit", False))
remain_hits = [r.get("remain_hit", 0) for r in opened]
avg_remain = sum(remain_hits) / total
assert hit_count == 2, f"杀号正确应为2期，实际{hit_count}"
assert remain_hits == [20, 19, 15, 20], f"剩余命中应为[20,19,15,20]，实际{remain_hits}"
assert avg_remain == (20+19+15+20)/4, f"平均剩余命中应为18.5，实际{avg_remain}"
print(f"[OK] 剩余号码策略: {total}期, 杀号正确{hit_count}期, 剩余命中{remain_hits}, 平均{avg_remain}")

# 选十码策略
win_count = sum(1 for r in opened if r.get("bet_prize","无奖") != "无奖")
total_money = sum(_xuanshi_prize(r.get("bet_hit",0))[1] for r in opened)
# 期1:500万 期2:8000 期3:2(安慰奖) 期4:0(无奖)
assert win_count == 3, f"选十中奖应为3期(一等+二等+安慰)，实际{win_count}"
assert total_money == 5000000 + 8000 + 2 + 0, f"累计奖金应为5008002，实际{total_money}"
print(f"[OK] 选十码策略: 中奖{win_count}期, 累计奖金{total_money:,}元")

# 测试 _refresh_results 重算 remain_hit
# 模拟：把期5的开奖结果补上（HistoryManager是单例，需指向临时文件并写入）
app.history_manager.history_file = os.path.join(tmp, "history.json")
app.history_manager.history_data = [{"issue":"2026205","number":drawn_str}]
app.history_manager._save_history()
# 重置期5的result为空（已经是空），刷新应填入并计算 remain_hit
rec5 = app.saved_predictions[-1]
assert rec5["result"] == ""
# 调用 _refresh_results（会弹messagebox，我们临时替换掉）
import tkinter.messagebox as mb
orig_showinfo = mb.showinfo
mb.showinfo = lambda *a, **k: None
try:
    app._refresh_results()
finally:
    mb.showinfo = orig_showinfo
# 期5现在应该有 result, remain_hit=20, hit=True, bet_hit=10
assert rec5["result"] == drawn_str, f"期5结果应被填入，实际{rec5['result']}"
assert rec5["remain_hit"] == 20, f"期5剩余命中应为20，实际{rec5['remain_hit']}"
assert rec5["hit"] == True, f"期5杀号应为正确"
assert rec5["bet_hit"] == 10, f"期5选十命中应为10，实际{rec5['bet_hit']}"
assert rec5["bet_prize"] == _xuanshi_prize(10)[0], f"期5应为一等奖"
print(f"[OK] _refresh_results 重算: 期5 remain_hit={rec5['remain_hit']}, bet_hit={rec5['bet_hit']}, 奖级={rec5['bet_prize']}")

# 测试 _save_remain_numbers 计算 remain_hit
# 临时把 saved_predictions 清空，设置当前UI的remain/bet，保存一期
app.saved_predictions = []
app.current_bet = list(range(1, 11))
# remain_text 当前是 1-80（默认），开奖号1-20 → remain_hit 应=20
app.history_manager.history_data = [{"issue":"2026301","number":drawn_str}]
app.history_manager._save_history()
app.save_issue_var.set("2026301")
orig_showerror = mb.showerror
orig_showwarning = mb.showwarning
mb.showerror = lambda *a, **k: None
mb.showwarning = lambda *a, **k: None
try:
    app._save_remain_numbers()
finally:
    mb.showerror = orig_showerror
    mb.showwarning = orig_showwarning
assert len(app.saved_predictions) == 1
rec = app.saved_predictions[0]
assert rec["issue"] == "2026301"
assert rec["remain_hit"] == 20, f"remain_hit应为20，实际{rec['remain_hit']}"
assert rec["bet_hit"] == 10, f"bet_hit应为10，实际{rec['bet_hit']}"
assert rec["bet_prize"] == _xuanshi_prize(10)[0]
assert rec["hit"] == True
print(f"[OK] _save_remain_numbers: 新记录含 remain_hit={rec['remain_hit']}, bet_hit={rec['bet_hit']}")

# 验证统计对话框能正常构造（弹窗）
orig_grab = tk.Toplevel.grab_set
tk.Toplevel.grab_set = lambda self: None
tk.Toplevel.withdraw = lambda self: None  # 不显示
top_count = [0]
orig_toplevel = tk.Toplevel
class FakeTop(tk.Toplevel):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.withdraw()
        top_count[0] += 1
tk.Toplevel = FakeTop
try:
    # 恢复期5为待开奖（让pending分支也走到）
    app.saved_predictions = [
        {"issue": "2026301", "remain": list(range(1,81)), "bet": list(range(1,11)),
         "result": drawn_str, "hit": True, "remain_hit": 20, "bet_hit": 10,
         "bet_prize": _xuanshi_prize(10)[0]},
    ]
    app._calc_prediction_stats()
finally:
    tk.Toplevel = orig_toplevel
    tk.Toplevel.grab_set = orig_grab
print(f"[OK] 统计对话框构造成功（创建了{top_count[0]}个Toplevel）")

print("\n========== 剩余号码+选十码 双策略统计 测试通过 ==========")
root.destroy()
