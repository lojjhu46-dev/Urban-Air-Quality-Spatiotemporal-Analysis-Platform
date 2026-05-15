import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
price = [44.98, 45.02, 44.32, 41.05, 42.08, 42.08, 42.08]

fig = plt.figure(figsize=(8, 6))

# 左侧 0.2、顶部 0.2，宽高均为 0.5
# add_axes 参数是 [left, bottom, width, height]
ax = fig.add_axes([0.2, 0.3, 0.5, 0.5])

ax.plot(week, price, marker="o", markersize=8)

# y 轴刻度标签格式：￥价格，保留一位小数
ax.yaxis.set_major_formatter(FuncFormatter(lambda y, pos: f"￥{y:.1f}"))

# x 轴刻度标签旋转 20 度
ax.set_xticks(range(len(week)))
ax.set_xticklabels(week, rotation=20)

# 刻度线向内，宽度为 2
ax.tick_params(axis="both", direction="in", width=2)

# 隐藏顶部和右侧脊柱
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.show()
