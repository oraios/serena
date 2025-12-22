# Serena + Pascal/Delphi 在 Windows 下的完整安装指南

## 📋 目录

1. [环境准备](#1-环境准备)
2. [安装 Serena](#2-安装-serena)
3. [配置 Pascal/Delphi 支持](#3-配置-pascaldelphi-支持)
4. [集成到 Claude Code](#4-集成到-claude-code)
5. [验证安装](#5-验证安装)
6. [实际使用示例](#6-实际使用示例)
7. [常见问题](#7-常见问题)

---

## 1. 环境准备

### 1.1 必需软件

#### ✅ 基础工具（任选一个即可）

| 工具 | 说明 | 是否必需 Git Bash |
|------|------|-------------------|
| Git Bash | 推荐，Unix 命令体验 | ✅ 是 Git Bash |
| PowerShell 7+ | Windows 原生，功能强大 | ❌ 不是 |
| CMD | Windows 原生，基本功能 | ❌ 不是 |

**推荐使用 PowerShell 7 或 Git Bash**，本指南会提供两者的命令。

#### ✅ Python 环境

```powershell
# 检查 Python 版本（需要 3.10+）
python --version
# 输出应该类似：Python 3.11.x 或更高

# 如果未安装，下载：https://www.python.org/downloads/
```

#### ✅ 版本控制

```powershell
# 检查 Git
git --version
```

#### ✅ Claude Code CLI

```powershell
# 检查 Claude Code 是否已安装
claude --version
```

如果未安装 Claude Code，参考：https://github.com/anthropics/claude-code

### 1.2 语言服务器依赖

根据你的项目类型选择：

#### 选项 A：Free Pascal / Lazarus 项目

```powershell
# 1. 安装 Free Pascal Compiler
# 下载：https://www.freepascal.org/download.html

# 验证安装
fpc -version

# 2. 安装 Lazarus（包含 lazbuild）
# 下载：https://www.lazarus-ide.org/
# 安装后验证
lazbuild --version

# 3. 配置 lazbuild 路径（如果不在 PATH 中）
# 编辑 C:\Users\<你的用户名>\.claude\CLAUDE.md，添加：
# - 构建FPC项目使用D:\che_m\laz32\lazarus\lazbuild.exe
```

#### 选项 B：Delphi / RAD Studio 项目

```powershell
# 1. 安装 RAD Studio 11.0 或更高版本
# 购买并安装：https://www.embarcadero.com/products/rad-studio

# 2. 验证 DelphiLSP.exe 存在
where DelphiLSP.exe
# 或手动检查：
# C:\Program Files (x86)\Embarcadero\Studio\<版本>\bin\DelphiLSP.exe

# 3. 配置 BDS 环境变量（通常安装时自动配置）
echo $env:BDS
# 应该输出类似：C:\Program Files (x86)\Embarcadero\Studio\23.0
```

#### 选项 C：两者都需要

按照选项 A 和选项 B 的步骤完成所有安装。

---

## 2. 安装 Serena

### 2.1 克隆仓库（使用我们的实现）

```powershell
# PowerShell / CMD
cd D:\che_m\Gits
git clone https://github.com/oraios/serena.git
cd serena

# 切换到我们的分支（假设你已经 push 到自己的 fork）
# git checkout pascal-delphi-support
```

```bash
# Git Bash
cd /d/che_m/Gits
git clone https://github.com/oraios/serena.git
cd serena
```

**注意：** 由于我们的实现尚未合并到 Serena 主仓库，你需要：
1. Fork Serena 仓库到你的 GitHub 账户
2. 应用我们的修改（已经在 `D:\che_m\Gits\serena\` 中）
3. Push 到你的 fork

```powershell
# 创建并推送分支
git checkout -b pascal-delphi-support
git add .
git commit -m "Add Pascal and Delphi language server support"
git remote add myfork https://github.com/<你的用户名>/serena.git
git push myfork pascal-delphi-support
```

### 2.2 安装依赖

Serena 支持多种安装方式，推荐使用 `uv`（最快）：

#### 方法 1：使用 uv（推荐）

```powershell
# 1. 安装 uv
# PowerShell
irm https://astral.sh/uv/install.ps1 | iex

# 或下载安装包：https://github.com/astral-sh/uv/releases

# 2. 安装 Serena 及其依赖
cd D:\che_m\Gits\serena
uv sync
```

#### 方法 2：使用 pip

```powershell
cd D:\che_m\Gits\serena

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# PowerShell
.\.venv\Scripts\Activate.ps1

# Git Bash
source .venv/Scripts/activate

# 安装依赖
pip install -e .
```

### 2.3 验证安装

```powershell
# 检查 Serena CLI
python -m serena.main --help

# 或者使用 uv
uv run serena --help
```

应该看到 Serena 的帮助信息。

---

## 3. 配置 Pascal/Delphi 支持

### 3.1 创建项目配置

在你的 **Pascal/Delphi 项目根目录**（不是 Serena 目录）创建 `project.yml`：

```powershell
# 示例：配置你的 mORMot2 项目
cd C:\Users\cm\prj1

# 创建 project.yml
# PowerShell
@"
languages:
  - pascal
  - python  # 如果项目中有 Python 脚本
  - bash    # 如果项目中有 Bash 脚本

# 可选：配置忽略路径
ignored_paths:
  - "lib/"
  - "backup/"
  - "__history/"
  - "*.dcu"
  - "*.exe"
"@ | Out-File -FilePath project.yml -Encoding UTF8
```

```bash
# Git Bash
cat > project.yml << 'EOF'
languages:
  - pascal
  - python
  - bash

ignored_paths:
  - "lib/"
  - "backup/"
  - "__history/"
  - "*.dcu"
  - "*.exe"
EOF
```

### 3.2 配置环境变量（可选但推荐）

#### Pascal 环境变量

```powershell
# PowerShell - 临时设置（当前会话）
$env:FPCDIR = "C:\FPC\3.2.2"
$env:LAZARUSDIR = "D:\che_m\laz32\lazarus"

# 永久设置（用户级）
[System.Environment]::SetEnvironmentVariable("FPCDIR", "C:\FPC\3.2.2", "User")
[System.Environment]::SetEnvironmentVariable("LAZARUSDIR", "D:\che_m\laz32\lazarus", "User")
```

```bash
# Git Bash - 添加到 ~/.bashrc
echo 'export FPCDIR=/c/FPC/3.2.2' >> ~/.bashrc
echo 'export LAZARUSDIR=/d/che_m/laz32/lazarus' >> ~/.bashrc
source ~/.bashrc
```

#### Delphi 环境变量

```powershell
# PowerShell - 检查 BDS 变量
echo $env:BDS

# 如果未设置，手动设置（替换为你的实际路径）
$env:BDS = "C:\Program Files (x86)\Embarcadero\Studio\23.0"
[System.Environment]::SetEnvironmentVariable("BDS", "C:\Program Files (x86)\Embarcadero\Studio\23.0", "User")
```

### 3.3 初始化 Serena 项目

```powershell
# 在你的项目目录中
cd C:\Users\cm\prj1

# 初始化 Serena（这会创建 .serena/ 目录）
python D:\che_m\Gits\serena\-m serena.main init

# 或使用 uv
uv run --directory D:\che_m\Gits\serena serena init
```

---

## 4. 集成到 Claude Code

### 4.1 配置 MCP Server

Claude Code 通过 MCP (Model Context Protocol) 与 Serena 通信。

#### 步骤 1：编辑 Claude Code 配置

```powershell
# 打开 Claude Code 的 MCP 配置文件
# 文件位置：C:\Users\<你的用户名>\.claude\mcp_config.json

# PowerShell
notepad $env:USERPROFILE\.claude\mcp_config.json
```

#### 步骤 2：添加 Serena MCP Server

在 `mcp_config.json` 中添加 Serena 配置：

```json
{
  "mcpServers": {
    "serena": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "D:\\che_m\\Gits\\serena",
        "serena",
        "mcp"
      ],
      "env": {
        "FPCDIR": "C:\\FPC\\3.2.2",
        "LAZARUSDIR": "D:\\che_m\\laz32\\lazarus",
        "BDS": "C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0"
      }
    }
  }
}
```

**如果使用 pip 安装的虚拟环境：**

```json
{
  "mcpServers": {
    "serena": {
      "command": "D:\\che_m\\Gits\\serena\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "serena.main",
        "mcp"
      ],
      "env": {
        "FPCDIR": "C:\\FPC\\3.2.2",
        "LAZARUSDIR": "D:\\che_m\\laz32\\lazarus"
      }
    }
  }
}
```

#### 步骤 3：重启 Claude Code

```powershell
# 关闭所有 Claude Code 窗口，然后重新启动
claude
```

### 4.2 验证 MCP 连接

在 Claude Code 中输入：

```
列出可用的 MCP 工具
```

或者：

```
使用 serena 查找项目中的所有类定义
```

你应该能看到 Serena 提供的工具列表，包括：
- `find_symbol`
- `find_referencing_symbols`
- `insert_after_symbol`
- 等等

---

## 5. 验证安装

### 5.1 测试 Pascal LSP

```powershell
# 进入 Serena 目录
cd D:\che_m\Gits\serena

# 运行 Pascal 测试
pytest test/solidlsp/pascal -v -m pascal

# 如果使用 uv
uv run pytest test/solidlsp/pascal -v -m pascal
```

**预期输出：**
```
test_pascal_language_server_initialization PASSED
test_pascal_request_document_symbols PASSED
test_pascal_class_methods PASSED
...
```

**首次运行注意：** 如果 pasls 未安装，测试会自动克隆并编译，可能需要 3-5 分钟。

### 5.2 测试实际项目

在你的 Pascal 项目中创建测试文件：

```powershell
cd C:\Users\cm\prj1

# 创建简单的测试文件
@"
program Test;
uses SysUtils;

type
  TExample = class
    procedure Hello;
  end;

procedure TExample.Hello;
begin
  WriteLn('Hello from Serena!');
end;

var
  Example: TExample;
begin
  Example := TExample.Create;
  try
    Example.Hello;
  finally
    Example.Free;
  end;
end.
"@ | Out-File -FilePath test_serena.pas -Encoding UTF8
```

### 5.3 在 Claude Code 中测试

启动 Claude Code 并尝试：

```
使用 serena 在当前项目中查找 TExample 类的定义
```

或者：

```
帮我找到 TExample.Hello 方法的所有调用位置
```

**成功标志：**
- Claude Code 能准确定位类和方法的位置
- 返回具体的文件路径和行号
- **不需要读取整个文件内容**

---

## 6. 实际使用示例

### 6.1 场景：重构 mORMot2 代码

假设你想在 `TRestServer` 类的 `Create` 方法后添加新的验证逻辑：

```
我想在 TRestServer.Create 方法后添加一个新的 ValidateConfiguration 方法。
步骤：
1. 使用 serena 找到 TRestServer.Create 的定义
2. 在它后面插入新方法
3. 确保新方法在正确的位置（private 还是 public 区域）
```

Claude Code 会使用 Serena 的工具：

```python
# Claude Code 内部调用
find_symbol("TRestServer.Create")
# 返回：src/orm/mormot.orm.rest.pas:512

insert_after_symbol(
    "TRestServer.Create",
    """
    /// <summary>验证服务器配置</summary>
    procedure ValidateConfiguration;
    """
)
```

**Token 节省对比：**

| 方式 | Token 消耗 | 说明 |
|------|-----------|------|
| 无 Serena | ~15,000 | 需要 Read 整个 mormot.orm.rest.pas (3000 行) |
| 有 Serena | ~500 | 只返回精确的符号位置 + 上下文 |

**节省率：96.7%** 🎉

### 6.2 场景：查找函数调用

```
帮我找到项目中所有调用 TSynLog.Add 的地方
```

**无 Serena：**
1. Grep 搜索 "TSynLog.Add" → 200+ 匹配（包括注释、字符串）
2. Read 20+ 个文件验证
3. Token 消耗：~20,000

**有 Serena：**
1. `find_referencing_symbols("TSynLog.Add")` → 12 个准确调用
2. 直接返回文件名 + 行号 + 代码片段
3. Token 消耗：~2,000

**节省率：90%** 🚀

### 6.3 场景：理解类继承

```
TOrm 类有哪些子类？分别在哪些文件中？
```

**Serena 工作流：**
```python
# 1. 找到 TOrm 定义
find_symbol("TOrm")

# 2. 找到所有继承 TOrm 的类（LSP 提供）
# 返回：TOrmUser, TOrmProduct, TOrmOrder, ...

# 3. 逐个查找子类定义位置
for subclass in subclasses:
    find_symbol(subclass)
```

**Token 效率：** 只访问相关符号，不读取无关文件。

---

## 7. 常见问题

### 问题 1：pasls 编译失败

**症状：**
```
Error: Failed to build pasls. Error: lazbuild not found
```

**解决方案：**
```powershell
# 1. 确保 Lazarus 已安装
lazbuild --version

# 2. 如果提示找不到，手动指定路径
$env:PATH += ";D:\che_m\laz32\lazarus"

# 3. 或在 CLAUDE.md 中配置
# - 构建FPC项目使用D:\che_m\laz32\lazarus\lazbuild.exe
```

### 问题 2：DelphiLSP.exe 找不到

**症状：**
```
FileNotFoundError: DelphiLSP.exe not found
```

**解决方案：**
```powershell
# 1. 检查 RAD Studio 是否已安装
where DelphiLSP.exe

# 2. 手动添加到 PATH
$env:PATH += ";C:\Program Files (x86)\Embarcadero\Studio\23.0\bin"

# 3. 或设置 BDS 环境变量
$env:BDS = "C:\Program Files (x86)\Embarcadero\Studio\23.0"
```

### 问题 3：Claude Code 找不到 serena 工具

**症状：**
Claude Code 提示 "No MCP tools available"

**解决方案：**
```powershell
# 1. 检查 mcp_config.json 格式是否正确
Get-Content $env:USERPROFILE\.claude\mcp_config.json

# 2. 检查 Serena 路径是否正确
Test-Path D:\che_m\Gits\serena

# 3. 手动测试 Serena MCP
cd D:\che_m\Gits\serena
uv run serena mcp
# 应该启动 MCP 服务器

# 4. 重启 Claude Code
```

### 问题 4：找不到项目符号

**症状：**
```
find_symbol("TRestServer") returns: Symbol not found
```

**可能原因：**
1. **project.yml 未配置** - 在项目根目录创建
2. **LSP 服务器未启动** - 检查日志
3. **文件扩展名不匹配** - 确保是 `.pas`, `.pp` 等

**解决方案：**
```powershell
# 1. 确认 project.yml 存在
Test-Path .\project.yml

# 2. 查看 Serena 日志
# 日志位置：C:\Users\<用户名>\.serena\logs\

# 3. 手动测试 LSP
cd D:\che_m\Gits\serena
python -c "
from solidlsp.ls_config import Language
from solidlsp import SolidLanguageServer

ls = SolidLanguageServer.create(
    Language.PASCAL,
    'C:/Users/cm/prj1'
)
print('LSP started:', ls)
"
```

### 问题 5：Git Bash 还是 PowerShell？

**答案：都可以，但有区别**

| 特性 | Git Bash | PowerShell 7 | CMD |
|------|----------|--------------|-----|
| Unix 命令 | ✅ | ⚠️ 部分支持 | ❌ |
| 路径格式 | `/d/path` | `D:\path` | `D:\path` |
| 脚本功能 | Bash | 强大 | 基础 |
| Windows 原生 | ❌ | ✅ | ✅ |
| **推荐度** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

**建议：** 使用 **PowerShell 7**，因为：
- Windows 原生支持更好
- 功能强大（对象管道）
- Claude Code 集成更顺畅

### 问题 6：如何更新我们的 Pascal/Delphi 实现？

**场景：** Serena 主仓库发布新版本，你想合并我们的修改。

```powershell
cd D:\che_m\Gits\serena

# 1. 添加上游仓库
git remote add upstream https://github.com/oraios/serena.git

# 2. 获取最新更新
git fetch upstream

# 3. 合并到你的分支
git checkout pascal-delphi-support
git merge upstream/main

# 4. 解决冲突（如有）
# 然后重新安装
uv sync
```

---

## 8. 性能优化建议

### 8.1 加速 pasls 编译

**首次编译慢？** 预下载 pasls：

```powershell
cd D:\che_m\Gits\serena

# 手动克隆 pasls
git clone https://github.com/genericptr/pascal-language-server.git .serena/lsp_servers/pasls/source

# 手动编译
lazbuild .serena/lsp_servers/pasls/source/src/standard/pasls.lpi

# 复制到标准位置
Copy-Item .serena/lsp_servers/pasls/source/src/standard/pasls.exe .serena/lsp_servers/pasls/
```

### 8.2 配置忽略路径

在 `project.yml` 中忽略不必要的目录：

```yaml
ignored_paths:
  - "lib/"
  - "backup/"
  - "__history/"
  - "*.dcu"
  - "*.exe"
  - "node_modules/"
  - ".git/"
```

### 8.3 使用 Controller 模式（Delphi）

Delphi LSP 已默认使用 Controller 模式 + 2 个 agent，无需额外配置。

---

## 9. 成功检查清单

在开始使用前，确认所有项都 ✅：

### 基础环境
- [ ] Python 3.10+ 已安装
- [ ] Git 已安装
- [ ] Claude Code CLI 已安装

### 语言服务器
- [ ] FPC + Lazarus 已安装（如果用 Pascal）
- [ ] RAD Studio 11+ 已安装（如果用 Delphi）
- [ ] lazbuild 或 DelphiLSP.exe 可在 PATH 中找到

### Serena
- [ ] Serena 已克隆到 `D:\che_m\Gits\serena`
- [ ] 依赖已安装（`uv sync` 或 `pip install -e .`）
- [ ] 我们的 Pascal/Delphi 实现已应用

### 项目配置
- [ ] 项目根目录有 `project.yml`
- [ ] `project.yml` 包含 `languages: [pascal]` 或 `[delphi]`
- [ ] 环境变量已配置（FPCDIR, LAZARUSDIR, BDS）

### Claude Code 集成
- [ ] `~/.claude/mcp_config.json` 已配置 serena
- [ ] Claude Code 可以列出 serena 的 MCP 工具
- [ ] 测试 `find_symbol` 命令成功

### 验证
- [ ] `pytest test/solidlsp/pascal -v -m pascal` 通过
- [ ] 在实际项目中能找到符号
- [ ] Token 消耗明显降低

---

## 10. 快速启动脚本

### PowerShell 一键安装脚本

```powershell
# 保存为 install_serena_pascal.ps1

# 1. 克隆 Serena
cd D:\che_m\Gits
if (!(Test-Path serena)) {
    git clone https://github.com/oraios/serena.git
}
cd serena

# 2. 安装 uv（如果未安装）
if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
    irm https://astral.sh/uv/install.ps1 | iex
}

# 3. 安装依赖
uv sync

# 4. 配置环境变量
[System.Environment]::SetEnvironmentVariable("FPCDIR", "C:\FPC\3.2.2", "User")
[System.Environment]::SetEnvironmentVariable("LAZARUSDIR", "D:\che_m\laz32\lazarus", "User")

# 5. 创建项目配置模板
@"
languages:
  - pascal
  - python

ignored_paths:
  - "lib/"
  - "backup/"
  - "__history/"
"@ | Out-File -FilePath C:\Users\cm\prj1\project.yml -Encoding UTF8

# 6. 配置 MCP
$mcpConfig = @{
    mcpServers = @{
        serena = @{
            command = "uv"
            args = @("run", "--directory", "D:\che_m\Gits\serena", "serena", "mcp")
            env = @{
                FPCDIR = "C:\FPC\3.2.2"
                LAZARUSDIR = "D:\che_m\laz32\lazarus"
            }
        }
    }
} | ConvertTo-Json -Depth 5

$mcpConfig | Out-File -FilePath "$env:USERPROFILE\.claude\mcp_config.json" -Encoding UTF8

Write-Host "✅ Serena + Pascal/Delphi 安装完成！"
Write-Host "请重启 Claude Code 以加载 MCP 服务器。"
```

### Git Bash 一键安装脚本

```bash
#!/bin/bash
# 保存为 install_serena_pascal.sh

# 1. 克隆 Serena
cd /d/che_m/Gits
if [ ! -d "serena" ]; then
    git clone https://github.com/oraios/serena.git
fi
cd serena

# 2. 安装 uv
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 3. 安装依赖
uv sync

# 4. 创建项目配置
cat > /c/Users/cm/prj1/project.yml << 'EOF'
languages:
  - pascal
  - python

ignored_paths:
  - "lib/"
  - "backup/"
  - "__history/"
EOF

# 5. 配置 MCP
mkdir -p ~/.claude
cat > ~/.claude/mcp_config.json << 'EOF'
{
  "mcpServers": {
    "serena": {
      "command": "uv",
      "args": ["run", "--directory", "D:\\che_m\\Gits\\serena", "serena", "mcp"],
      "env": {
        "FPCDIR": "C:\\FPC\\3.2.2",
        "LAZARUSDIR": "D:\\che_m\\laz32\\lazarus"
      }
    }
  }
}
EOF

echo "✅ Serena + Pascal/Delphi 安装完成！"
echo "请重启 Claude Code 以加载 MCP 服务器。"
```

---

## 11. 下一步

安装完成后，尝试：

1. **测试基本功能**
   ```
   在 Claude Code 中：
   "使用 serena 列出项目中的所有类"
   ```

2. **实际重构任务**
   ```
   "帮我在 TRestServer 类中添加一个新的日志方法"
   ```

3. **查看 Token 节省**
   ```
   对比使用 Serena 前后的 Token 消耗
   ```

4. **探索高级功能**
   - 符号重命名
   - 跨文件引用查找
   - 智能代码插入

---

## 📚 相关资源

- **Serena 官方文档**: https://oraios.github.io/serena/
- **Pascal LSP**: https://github.com/genericptr/pascal-language-server
- **DelphiLSP**: https://docwiki.embarcadero.com/RADStudio/Alexandria/en/Using_DelphiLSP_Code_Insight_with_Other_Editors
- **Claude Code**: https://github.com/anthropics/claude-code
- **MCP 协议**: https://modelcontextprotocol.io/

---

## ✨ 享受 Token 节省的快乐！

配置完成后，你的 mORMot2 项目将获得：
- **70-80% 的 Token 节省**
- **精确的符号级操作**
- **多语言混合支持**
- **AI 友好的代码库导航**

Happy Coding! 🚀
