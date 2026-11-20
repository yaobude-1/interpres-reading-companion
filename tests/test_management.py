"""验证生词本删除和「再次启动打开设置」接口。"""

from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.server import ApiServer  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".mgmt"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    cfg.data["server_port"] = 18795
    cfg.save()
    service = Service(cfg)

    print("\n[生词本删除]")
    ids = [
        service.add_vocab(lang="en", word="alpha", lemma="alpha", meaning="甲")["id"],
        service.add_vocab(lang="en", word="beta", lemma="beta", meaning="乙")["id"],
        service.add_vocab(lang="fr", word="gamma", lemma="gamma", meaning="丙")["id"],
    ]
    check("先有 3 个", service.store.word_count() == 3, str(service.store.word_count()))
    removed = service.store.delete_words([ids[0]])
    check("删掉 1 个", removed == 1, str(removed))
    check("剩 2 个", service.store.word_count() == 2, str(service.store.word_count()))
    left = [w["lemma"] for w in service.store.list_words()]
    check("删的是选中的那个", "alpha" not in left and set(left) == {"beta", "gamma"}, str(left))
    removed = service.store.delete_words([ids[1], ids[2]])
    check("批量删除", removed == 2 and service.store.word_count() == 0, str(removed))

    print("\n[再次启动 → 打开设置接口]")
    called: list[int] = []
    server = ApiServer(service, port=18795, token="tok", on_show_settings=lambda: called.append(1))
    server.start()
    time.sleep(0.2)

    def post(path: str, token: str):
        req = urllib.request.Request(
            f"http://127.0.0.1:18795{path}",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json", "X-RC-Token": token},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    result = post("/api/show-settings", "tok")
    check("接口返回 ok", result.get("ok") is True, str(result))
    check("回调被触发", len(called) == 1, str(called))

    try:
        post("/api/show-settings", "wrong")
        check("错误 token 被拒", False, "竟然通过了")
    except urllib.error.HTTPError as exc:  # noqa: F821
        check("错误 token 被拒", exc.code == 401, str(exc.code))

    server.stop()
    service.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
