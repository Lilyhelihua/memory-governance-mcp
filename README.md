# memory-governance-mcp

MCP server for **auditable long-term memory** in AI workspaces — JSON-RPC over stdio, Python stdlib only.

给 AI 工作区装上「可版本化、可审计的长期记忆」的 MCP 服务器。不联网、无第三方依赖，四个工具，一条 stdio 管道。

## 为什么需要它

多个 agent、多个会话、多个定时任务写同一批记忆文件时，常见结局是：互相覆盖、改错没法回滚、被粘贴进来的外部内容带着指令一起进记忆。这个服务器把写入变成**哈希校验 + 快照 + 审计日志链**，冲突显式报错而不是静默覆盖。

## 四个工具

| 工具 | 作用 |
|---|---|
| `memory_status` | 列出所有受管文件的 rev / hash / 状态（一致 / 已漂移 / 未入库）|
| `memory_get` | 读取某文件的当前内容与库内快照 |
| `memory_scan` | 写入前体检：不落盘，只判这段文本能不能进记忆 |
| `memory_put` | 带哈希的乐观并发写入：`--expect` 不匹配则拒绝（exit 3），必须合并后重写 |

## 快速开始

把它注册进你的 MCP 配置（WorkBuddy / Claude Desktop / 任何 stdio 客户端）：

```json
{
  "mcpServers": {
    "memory-governance": {
      "command": "python",
      "args": ["<你的目录>/mcp_server.py"]
    }
  }
}
```

前提：Python 3.9+，无第三方依赖。路径换成你本机放置 `mcp_server.py` 的位置。

## 设计决定

**服务器不实现任何记忆逻辑，只通过 subprocess 调用同目录的 `ctx.py`。** 行为只有一份——CLI 和 MCP 永远不会说出两个不同的结果，也不会出现"两个入口各修各的 bug"。

配套的审计机制（内容寻址快照、HMAC 索引签名、日志哈希链、做梦层无写权限）由 `ctx.py` / `dream.py` 承载，见同名 Skill：**记忆治理（memory-governance）**，已在 [腾讯云 SkillHub](https://skillhub.cloud.tencent.com/) 上架。

## 边界

- 不联网、不发请求、不装包
- 只写你指定工作区里的 `.workbuddy/context/` 与 `.workbuddy/memory/`
- 唯一的删除动作：回收自己生成的未引用快照（`os.remove`），永不删这两处以外的文件

## License

MIT
