# Codex Chat Recovery

从 Codex 本地保存的 `.jsonl` 会话文件中恢复用户与助手聊天记录，并导出为便于阅读和备份的 Markdown 或 JSON。

这个工具只读取源文件，不会修改 `~/.codex`、Codex 数据库或原始会话。

## 支持能力

- 扫描一个会话文件或整个 `~/.codex/sessions` 目录
- 从 `response_item/message` 恢复用户和助手消息
- 兼容旧版仅包含 `event_msg/user_message`、`agent_message` 的记录
- 忽略工具调用、推理内容、系统和开发者指令，以及应用自动注入的环境信息
- 默认隐藏助手的过程更新（commentary），可按需包含
- 遇到损坏的 JSONL 行时继续恢复其余内容并报告警告
- 按关键词查找并批量导出 Markdown 或 JSON

## 使用方法

要求 Python 3.9 或更高版本，不依赖第三方包。

```bash
cd codex-chat-recovery

# 查看最近可恢复的 30 个会话
python3 recover.py scan

# 搜索聊天内容
python3 recover.py scan --query "关键词" --limit 100

# 查看单个会话；FILE 来自 scan 输出的最后一列
python3 recover.py show FILE

# 将所有会话导出为 Markdown
python3 recover.py export --output ./recovered-chats

# 从迁移过来的备份目录恢复，并导出为 JSON
python3 recover.py export /path/to/codex-backup/sessions \
  --output ./recovered-json --format json

# 如需保留聊天过程中的 commentary 更新
python3 recover.py export --output ./recovered-chats --include-commentary
```

如果设置了 `CODEX_HOME`，默认读取 `$CODEX_HOME/sessions`；否则读取 `~/.codex/sessions`。

## 换机恢复建议

1. 在旧电脑完整复制 `~/.codex/sessions`，不要只复制数据库文件。
2. 在新电脑上先把备份放到一个单独目录。
3. 用本工具导出为 Markdown/JSON，确认消息数量和恢复警告。
4. 不要手动覆盖或编辑新电脑正在使用的 Codex 数据库。

该工具恢复的是可阅读、可搜索的聊天副本，不会把会话重新注册到 Codex 应用侧边栏。Codex 内部格式并非稳定的公开导入接口；当格式变化时，应更新解析器而不是修改原始文件。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
