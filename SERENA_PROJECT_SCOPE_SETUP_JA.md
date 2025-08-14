# Serena MCPサーバーのプロジェクトスコープ登録ガイド

## 概要

このドキュメントでは、各プロジェクトのカレントディレクトリからSerena MCPサーバーをプロジェクトスコープで登録する方法を説明します。プロジェクトスコープで登録することで、プロジェクト固有の設定を維持しながら、Claude Codeとの統合を最適化できます。

## プロジェクトスコープ登録コマンド

### 基本コマンド構文

プロジェクトディレクトリに移動後、以下のコマンドを実行します：

```bash
# プロジェクトディレクトリに移動
cd /path/to/your/project

# Serenaをプロジェクトスコープで登録（ローカルインストールの場合）
claude mcp add serena -s project -- uv run --directory /path/to/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# uvxを使用する場合（リモートインストール）
claude mcp add serena -s project -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)
```

### 重要なオプション説明

- `-s project` または `--scope project`: プロジェクトスコープで登録することを指定
- `--context ide-assistant`: Claude Code専用のコンテキストを使用
- `--project $(pwd)`: 現在のディレクトリをプロジェクトとして自動的に指定

## プロジェクトスコープの仕組み

### 1. 設定ファイルの生成

プロジェクトスコープで登録すると、プロジェクトルートに `.mcp.json` ファイルが作成されます：

```json
{
  "mcpServers": {
    "serena": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "ide-assistant",
        "--project",
        "${PWD}"
      ],
      "env": {}
    }
  }
}
```

### 2. 環境変数の展開

`.mcp.json` では以下の環境変数展開がサポートされています：

- `${VAR}`: 環境変数VARの値に展開
- `${VAR:-default}`: VARが設定されていればその値、なければdefaultを使用

例：
```json
{
  "mcpServers": {
    "serena": {
      "command": "${UV_PATH:-uvx}",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "ide-assistant",
        "--project",
        "${PROJECT_ROOT:-$(pwd)}"
      ]
    }
  }
}
```

## 実践的な使用例

### 1. 新規プロジェクトの場合

```bash
# プロジェクトディレクトリを作成
mkdir my-new-project
cd my-new-project

# Gitリポジトリを初期化
git init

# Serenaをプロジェクトスコープで登録
claude mcp add serena -s project -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# .mcp.jsonをGitに追加（チーム共有用）
git add .mcp.json
git commit -m "Add Serena MCP configuration"
```

### 2. 既存プロジェクトの場合

```bash
# 既存プロジェクトに移動
cd /path/to/existing/project

# 現在の状態を確認
git status

# Serenaをプロジェクトスコープで登録
claude mcp add serena -s project -- uv run --directory ~/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# プロジェクトをインデックス化（大規模プロジェクトの場合）
uv run --directory ~/serena serena project index
```

### 3. Dockerを使用する場合

```bash
cd /path/to/your/project

# Dockerでプロジェクトスコープ登録
claude mcp add serena -s project -- docker run --rm -i --network host -v $(pwd):/workspaces/project ghcr.io/oraios/serena:latest serena start-mcp-server --transport stdio --context ide-assistant --project /workspaces/project
```

## プロジェクト固有の設定

### 1. `.serena/project.yml` の自動生成

初回アクティベーション時に、プロジェクトディレクトリに `.serena/project.yml` が自動生成されます：

```yaml
name: my-project  # プロジェクト名（ディレクトリ名がデフォルト）
read_only: false  # 読み取り専用モード
excluded_tools: []  # プロジェクトで除外するツール
included_optional_tools: []  # 有効にするオプショナルツール
language_servers:  # 言語サーバー設定
  python:
    enabled: true
  typescript:
    enabled: true
```

### 2. プロジェクト設定のカスタマイズ

```yaml
# .serena/project.yml
name: my-awesome-project
read_only: false
excluded_tools:
  - execute_shell_command  # シェルコマンド実行を無効化
included_optional_tools:
  - initial_instructions  # 初期指示ツールを有効化
tool_timeout: 300  # タイムアウトを5分に設定
```

## チーム共有のベストプラクティス

### 1. 共有設定の管理

```bash
# .mcp.jsonをバージョン管理に追加
git add .mcp.json
git commit -m "Add team-shared Serena configuration"

# プロジェクト固有の設定も共有
git add .serena/project.yml
git commit -m "Configure Serena project settings"

# 個人設定は除外
echo ".serena/memories/" >> .gitignore
echo ".serena/cache/" >> .gitignore
git add .gitignore
git commit -m "Ignore personal Serena files"
```

### 2. チームメンバーへの指示

READMEに以下を追加：

```markdown
## Serena セットアップ

このプロジェクトはSerena MCPサーバーを使用しています。

### 初回セットアップ
1. Claude Codeをインストール
2. プロジェクトをクローン
3. プロジェクトディレクトリで以下を実行：
   ```bash
   # MCPサーバーの承認
   claude mcp reset-project-choices
   
   # Claude Codeを起動し、プロジェクトを開く
   claude /path/to/project
   ```
```

## スコープ管理コマンド

### 登録済みサーバーの確認

```bash
# すべてのスコープのサーバーを表示
claude mcp list

# プロジェクトスコープのみ表示
claude mcp list -s project
```

### サーバーの削除

```bash
# プロジェクトスコープのサーバーを削除
claude mcp remove serena -s project
```

### 設定の確認

```bash
# 特定のサーバーの詳細を表示
claude mcp get serena -s project
```

## トラブルシューティング

### 1. 承認のリセット

プロジェクトスコープのMCPサーバーは初回使用時に承認が必要です：

```bash
# すべてのプロジェクト承認をリセット
claude mcp reset-project-choices
```

### 2. 複数インスタンスの管理

同じプロジェクトで複数のSerenaインスタンスが起動している場合：

1. Webダッシュボードで確認：`http://localhost:24282/dashboard/`
2. 不要なインスタンスを停止
3. Claude Codeを再起動

### 3. パスの問題

Windows環境では、パスの区切り文字に注意：

```bash
# Windows（PowerShell）
claude mcp add serena -s project -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $PWD

# Windows（Git Bash）
claude mcp add serena -s project -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)
```

## まとめ

プロジェクトスコープでのSerena登録により：

1. **チーム共有**: `.mcp.json`を通じて設定を共有
2. **プロジェクト固有設定**: 各プロジェクトに最適化された設定
3. **自動プロジェクト認識**: `$(pwd)`による現在のディレクトリの自動認識
4. **環境変数対応**: 柔軟な設定管理
5. **バージョン管理統合**: Gitでの設定管理

これにより、各プロジェクトで最適なSerena環境を構築し、チーム全体で一貫した開発体験を実現できます。