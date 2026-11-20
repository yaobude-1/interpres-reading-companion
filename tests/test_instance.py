"""验证单实例锁和端口独占。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.instance import SingleInstance  # noqa: E402
from rc.server import _LocalServer  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f" {detail}"))
    if not cond:
        fails.append(name)


print("[单实例锁]")
a = SingleInstance("Local\\RCTestMutex")
b = SingleInstance("Local\\RCTestMutex")
check("第一个拿到锁", a.acquired is True)
check("第二个被拒绝", b.acquired is False, f"b.acquired={b.acquired}")
a.release()
c = SingleInstance("Local\\RCTestMutex")
check("释放后可再获取", c.acquired is True)
c.release()
b.release()

print("\n[端口独占]")
s1 = _LocalServer(("127.0.0.1", 18790), None)
s1.server_close()

s1 = _LocalServer(("127.0.0.1", 18790), None)
try:
    s2 = _LocalServer(("127.0.0.1", 18790), None)
    s2.server_close()
    check("同一端口不能绑两次", False, "第二个居然绑成功了")
except OSError as exc:
    check("同一端口不能绑两次", True, str(exc))
finally:
    s1.server_close()

print()
print("失败项：", fails if fails else "无")
sys.exit(1 if fails else 0)
