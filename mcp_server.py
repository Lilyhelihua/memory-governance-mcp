#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_server.py — 把 ctx.py 的记忆治理能力暴露成 MCP 工具。

传输：stdio，一行一条 JSON-RPC 2.0 消息（MCP stdio transport）。
依赖：仅 Python 标准库。不联网、不开端口、不调 shell。

设计上只做一件事：把 MCP 的 tools/call 翻译成 `python ctx.py ...` 子进程调用。
不在这里复刻体检、锁、哈希比对的逻辑——那些在 ctx.py 里只有一份，
命令行走什么行为，MCP 调用就是什么行为。

工具：
  memory_status  看哪些文件已入库、哪些漂移了
  memory_get     读某个文件的当前版本（或指定 rev）
  memory_scan    只体检不落盘，返回风险清单
  memory_put     带版本号写入；版本对不上就拒绝（乐观并发）
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = os.path.join(HERE, "ctx.py")
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "memory-governance", "version": "0.1.0"}

# ctx.py 的中文输出在管道里会走 locale 编码，统一钉成 utf-8
def _env():
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def run_ctx(args, stdin_data=None):
    """跑一次 ctx.py，返回 (exit_code, stdout, stderr)。"""
    p = subprocess.run(
        [sys.executable, CTX] + args,
        input=stdin_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(),
    )
    return (
        p.returncode,
        p.stdout.decode("utf-8", "replace"),
        p.stderr.decode("utf-8", "replace"),
    )


TOOLS = [
    {
        "name": "memory_status",
        "description": (
            "列出受管记忆文件的入库状态：每个文件的版本号（rev）、内容哈希、"
            "以及工作区内容是否已经偏离已入库的版本。用于判断能不能安全写入。"
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "memory_get",
        "description": (
            "读取某个受管文件的当前内容，或指定版本号的历史内容。"
            "返回内容与该版本的短哈希，写入时要把这个哈希作为 expect 传回去。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对工作区根目录的文件路径"},
                "rev": {"type": "integer", "description": "版本号；不填则取当前版本"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_scan",
        "description": (
            "写入前的体检：检查内容里有没有提示注入话术、隐藏字符、"
            "破坏性命令、凭据泄露。只返回风险清单，不落盘、不改变任何文件。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "准备写入的目标路径"},
                "content": {"type": "string", "description": "准备写入的正文"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_put",
        "description": (
            "写入一个新版本。必须带上你读到时的哈希作为 expect；"
            "如果文件在此期间被别人改过，写入会被拒绝并返回冲突，"
            "而不是静默覆盖。expect 传 new 表示要求这是个新文件。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对工作区根目录的文件路径"},
                "content": {"type": "string", "description": "新版本正文"},
                "expect": {
                    "type": "string",
                    "description": "你读到的版本哈希（可用短前缀）；new 表示必须是新文件",
                },
                "by": {"type": "string", "description": "写入者标识，默认 agent"},
                "msg": {"type": "string", "description": "本次改动说明"},
                "allow_suspect": {
                    "type": "boolean",
                    "description": "高危内容放行开关，默认 false；放行会在日志里留痕",
                },
            },
            "required": ["path", "content", "expect"],
            "additionalProperties": False,
        },
    },
]


def tool_result(exit_code, out, err):
    text = out.strip() if out.strip() else err.strip()
    body = {"content": [{"type": "text", "text": text or "(无输出)"}]}
    if exit_code != 0:
        body["isError"] = True
        if out.strip() and err.strip():
            body["content"][0]["text"] = out.strip() + "\n" + err.strip()
    return body


def call_tool(name, a):
    if name == "memory_status":
        return tool_result(*run_ctx(["status", "--json"]))

    if name == "memory_get":
        args = ["get", a["path"]]
        if a.get("rev"):
            args += ["--rev", str(a["rev"])]
        return tool_result(*run_ctx(args))

    if name == "memory_scan":
        return tool_result(
            *run_ctx(["put", a["path"], "--stdin", "--dry-run"],
                     stdin_data=a["content"].encode("utf-8"))
        )

    if name == "memory_put":
        args = [
            "put", a["path"], "--stdin",
            "--expect", a["expect"],
            "--by", a.get("by") or "agent",
            "-m", a.get("msg") or "",
        ]
        if a.get("allow_suspect"):
            args.append("--allow-suspect")
        return tool_result(*run_ctx(args, stdin_data=a["content"].encode("utf-8")))

    raise KeyError("未知工具：%s" % name)


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    # 通知类消息不需要回复
    if isinstance(method, str) and method.startswith("notifications/"):
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def fail(code, message):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method == "ping":
        return ok({})

    if method == "tools/list":
        return ok({"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            return ok(call_tool(name, args))
        except KeyError as e:
            return fail(-32602, str(e))
        except Exception as e:  # noqa: BLE001 - 任何内部异常都要回给客户端，不能让进程死
            return ok({
                "content": [{"type": "text", "text": "服务端异常：%s" % e}],
                "isError": True,
            })

    return fail(-32601, "不支持的方法：%s" % method)


def main():
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(req, dict):
            continue
        resp = handle(req)
        if resp is None:
            continue
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
