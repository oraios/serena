# Claude Code統合のためのSerenaセットアップ分析

## エグゼクティブサマリー

本ドキュメントは、Claude Code専用のローカルインストレーションとしてSerenaを使用する際のセットアップ手順について包括的な分析を提供します。インストール要件、設定の詳細、MCPサーバー統合の詳細、および最適なセットアップの推奨事項をカバーしています。

## コアアーキテクチャの概要

Serenaは、Language Server Protocol（LSP）統合を通じてセマンティックなコード分析と編集機能を提供するModel Context Protocol（MCP）サーバーとして動作します。Claude Codeと共に使用する場合、Claude Codeクライアントによって管理されるサブプロセスとして機能し、stdioまたはSSEトランスポートプロトコルを介して通信します。

### 主要コンポーネント

1. **SerenaAgent** (`src/serena/agent.py`): プロジェクト、ツール、ユーザーインタラクションを管理する中央オーケストレーター
2. **SolidLanguageServer** (`src/solidlsp/ls.py`): LSP実装の統一ラッパー
3. **MCPサーバー** (`src/serena/mcp.py`): FastMCPベースのサーバー実装
4. **ツールシステム** (`src/serena/tools/`): コード分析と操作のための包括的なツールセット

## インストール要件

### システムの前提条件

1. **Pythonバージョン**: 3.11（`pyproject.toml`で指定されている通り厳密に必要）
   ```
   requires-python = ">=3.11, <3.12"
   ```

2. **パッケージマネージャー**: UV（依存関係管理に必要）
   - インストール: `curl -LsSf https://astral.sh/uv/install.sh | sh`

3. **依存関係**（UVによって自動管理）：
   - mcp==1.12.3（Model Context Protocol）
   - pyright、overrides、python-dotenv
   - flask（Webダッシュボード用）
   - pydantic、pyyaml、jinja2
   - 言語固有のサーバー（オンデマンドでダウンロード）

### 言語サーバーの要件

Serenaは13以上のプログラミング言語をサポートし、インストール要件は言語によって異なります：

**追加インストール不要**（すぐに使用可能）：
- Python（Pyright経由）
- TypeScript/JavaScript
- PHP
- Rust
- C#
- Java
- Elixir（Elixir/NextLSの別途インストールが必要）
- Clojure
- C/C++
- Lean 4（別途Leanインストールが必要）

**手動インストールが必要**：
- Go（`go`と`gopls`が必要）
- Ruby、Kotlin、Dart（未テスト）

## Claude Code統合の詳細

### 1. MCPサーバー設定

Claude CodeはMCP設定で特定の構成が必要です：

```bash
claude mcp add serena -- <serena-mcp-server-command> --context ide-assistant --project $(pwd)
```

### 2. コンテキスト選択：`ide-assistant`

`ide-assistant`コンテキストはClaude Code統合専用に設計されています：

```yaml
# src/serena/resources/config/contexts/ide-assistant.yml
description: 非シンボリック編集ツールと一般的なシェルツールは除外されます
excluded_tools:
  - create_text_file
  - read_file
  - delete_lines
  - replace_lines
  - insert_at_line
  - execute_shell_command
  - prepare_for_new_conversation
  - summarize_changes
  - get_current_config
```

**理由**: Claude Codeには独自のファイルI/Oとシェル実行機能があるため、Serenaはツールの競合を避けるためにセマンティック/シンボリック操作に専念します。

### 3. トランスポートプロトコル

- **デフォルト**: stdio（標準入出力通信）
- **代替**: SSE（Server-Sent Events）HTTP通信用

Claude Codeの場合、stdioがネイティブなトランスポートメカニズムとして推奨されます。

### 4. 起動コマンドの構造

ローカルインストールの完全な起動コマンド：

```bash
# ローカルインストールを使用
claude mcp add serena -- uv run --directory /path/to/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# uvxを使用（リモートインストール）
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)
```

## 設定階層

1. **コマンドライン引数**（最高優先度）
2. **プロジェクト設定**（`.serena/project.yml`）
3. **ユーザー設定**（`~/.serena/serena_config.yml`）
4. **デフォルト設定**

### 必須設定オプション

```yaml
# ~/.serena/serena_config.yml
gui_log_window: False  # Claude Codeには推奨されません
web_dashboard: True    # モニタリングに推奨
web_dashboard_open_on_launch: True
log_level: 20  # INFOレベル
trace_lsp_communication: False  # デバッグ時に有効化
tool_timeout: 240  # デフォルト4分
record_tool_usage_stats: True  # ダッシュボード分析用
```

## MCPサーバー実装の詳細

### 1. ツール登録

SerenaはツールをMCP互換形式に動的に変換します：

```python
# src/serena/mcp.py:60-100
@staticmethod
def make_mcp_tool(tool: Tool) -> MCPTool:
    # 関数メタデータを抽出
    # 説明用のドキュメント文字列を解析
    # パラメータスキーマを作成
    # エラーハンドリングで実行をラップ
```

### 2. ログ設定

- **stdoutは決して使用しない**（MCP通信用に予約）
- stderr、メモリバッファ、ファイルにログ出力
- Webダッシュボードは`http://localhost:24282/dashboard/`でアクセス可能

### 3. プロセスライフサイクル

- Claude Codeによってサブプロセスとして起動
- ツール呼び出し間で永続的な状態を維持
- 自動言語サーバー管理
- ダッシュボードまたはクライアント終了による優雅なシャットダウン

## Claude Code用の最適化

### 1. メモリ管理

- `.serena/memories/`に永続的なプロジェクト知識
- 新規プロジェクトの自動オンボーディングプロセス
- コンテキスト認識型メモリ取得

### 2. トークン効率

- シンボリック操作でトークン使用を最小化
- フルファイルアクセスよりターゲット指向のコード読み取り
- 言語サーバー結果のインテリジェントなキャッシング

### 3. ツール選択

`ide-assistant`コンテキストでSerenaが提供するもの：
- **シンボリックナビゲーション**: `find_symbol`、`find_referencing_symbols`
- **コード概要**: `get_symbols_overview`
- **セマンティック編集**: `replace_symbol_body`、`insert_before_symbol`
- **パターン検索**: `search_for_pattern`
- **メモリ操作**: プロジェクト知識の読み書き

### 4. プロジェクトアクティベーション

2つの方法：
1. **起動パラメータ**: `--project /path/to/project`
2. **実行時アクティベーション**: `activate_project`ツール経由

## Claude Code統合のベストプラクティス

### 1. 初期セットアップ

1. UVパッケージマネージャーをインストール
2. Serenaリポジトリをローカルにクローン
3. 適切なコマンドでClaude Codeを設定
4. モニタリング用のWebダッシュボードを有効化
5. 常に`--context ide-assistant`を設定

### 2. プロジェクトワークフロー

1. クリーンなgit状態から開始
2. 大規模プロジェクトをインデックス化：`uv run serena project index`
3. オンボーディングプロセスの完了を許可
4. 永続的な知識にメモリを使用
5. ダッシュボード経由でツール使用をモニタリング

### 3. パフォーマンス最適化

- GUIログウィンドウを無効化（Webダッシュボードを使用）
- 適切なツールタイムアウトを設定
- ツール使用統計を有効化
- プロジェクト固有の設定を使用

### 4. トラブルシューティング

- `http://localhost:24282/dashboard/`でダッシュボードを確認
- LSPの問題には`trace_lsp_communication`を有効化
- 言語サーバーのインストールを確認
- ダッシュボードでメモリ使用をモニタリング

## セキュリティの考慮事項

1. **ツール実行**: すべてのツールはClaude Codeで明示的な許可が必要
2. **ファイルアクセス**: プロジェクトディレクトリと設定されたパスに制限
3. **シェルコマンド**: `ide-assistant`コンテキストでは無効
4. **ネットワークアクセス**: 言語サーバーのダウンロードのみ

## Claude Codeのユニークな利点

1. **無料ティアの互換性**: Claudeの無料ティアで動作
2. **セマンティック理解**: テキストベースではなくLSPベースの操作
3. **トークン効率**: シンボリック操作による最小限のコンテキスト使用
4. **永続的な知識**: プロジェクト固有のメモリシステム
5. **マルチ言語サポート**: 13以上の言語をすぐに使用可能

## 結論

SerenaとClaude Codeの統合は、セマンティックなコード理解とAIアシスタンスの強力な組み合わせを表しています。ローカルインストールアプローチと`ide-assistant`コンテキストの組み合わせにより、ツールの競合を避けながら最適なパフォーマンスを提供します。MCPサーバーアーキテクチャは信頼性の高い通信を保証し、LSP統合により、追加のAPIコストなしでClaude Codeの機能を大幅に強化する正確でコンテキスト認識型のコード操作を可能にします。