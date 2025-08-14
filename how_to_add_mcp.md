claude mcp add -s project serena -- uv run --isolated --directory /home/ubuntu/serena serena start-mcp-server --context ide-assistant --project $(pwd)


# プロジェクトディレクトリで
cd /path/to/your/project

# MCPサーバーを登録
claude mcp add -s project serena -- uv run --isolated --directory /home/ubuntu/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# インデックスを作成
uv run --isolated --directory /home/ubuntu/serena serena project index

# ~/.bashrc または ~/.zshrc に追加
alias serena-dev='uv run --isolated --directory /home/ubuntu/serena serena'
serena-dev project index



`~/.bashrc`
```bash
# Serena development aliases
alias serena-dev='uv run --isolated --directory /home/ubuntu/serena serena'
alias serena-index='serena-dev project index'
alias serena-config='serena-dev config edit'
alias serena-tools='serena-dev tools list'
```

```
# プロジェクトディレクトリへ移動
cd /path/to/your/lean4/project

# MCPサーバーを登録
claude mcp add -s project serena -- uv run --isolated --directory /home/ubuntu/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# インデックスを作成
serena-index
```
