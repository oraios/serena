# Pascal 和 Delphi 语言支持实现文档

## 概述

本文档记录了为 Serena 项目添加 Pascal (Free Pascal) 和 Delphi 语言支持的实现过程。

## 实现日期

2025-12-16

## 实现内容

### 1. 新增语言服务器实现

#### 1.1 Pascal Language Server (`pascal_server.py`)

**文件路径**: `src/solidlsp/language_servers/pascal_server.py`

**功能特性**:
- 支持 Free Pascal Compiler (FPC) 和 Lazarus IDE
- 使用 `pasls` (Pascal Language Server) 作为 LSP 后端
- 自动检测和安装 pasls:
  - 首先检查 PATH 环境变量
  - 检查已知安装位置
  - 如果未找到，自动使用 lazbuild 从源码编译
- 支持的文件扩展名: `.pas`, `.pp`, `.lpr`, `.lfm`, `.inc`
- 忽略的目录: `lib`, `backup`, `__history`, `__recovery`, `bin`

**环境要求**:
- Free Pascal Compiler (fpc)
- Lazarus (用于编译 pasls)
- Git (用于克隆 pasls 仓库)

#### 1.2 Delphi Language Server (`delphi_server.py`)

**文件路径**: `src/solidlsp/language_servers/delphi_server.py`

**功能特性**:
- 支持 Embarcadero RAD Studio 11.0 或更高版本
- 使用 `DelphiLSP.exe` (Embarcadero 官方 LSP 服务器)
- 自动检测 DelphiLSP.exe:
  - 首先检查 PATH 环境变量
  - 检查标准 RAD Studio 安装位置
  - 使用 BDS 环境变量定位
- 支持的文件扩展名: `.pas`, `.dpr`, `.dfm`, `.dpk`, `.inc`
- 忽略的目录: `__history`, `__recovery`, `win32`, `win64`, `debug`, `release`, `lib`, `dcu`, `obj`
- 服务器模式: Controller 模式 (2 个并行 agent 进程)

**环境要求**:
- RAD Studio 11.0 或更高版本

### 2. 配置文件修改

#### 2.1 `ls_config.py` 修改

**添加的语言枚举**:
```python
PASCAL = "pascal"
DELPHI = "delphi"
```

**文件扩展名匹配**:
- Pascal: `*.pas`, `*.pp`, `*.lpr`, `*.lfm`, `*.inc`
- Delphi: `*.pas`, `*.dpr`, `*.dfm`, `*.dpk`, `*.inc`

**LSP 类关联**:
```python
case self.PASCAL:
    from solidlsp.language_servers.pascal_server import PascalLanguageServer
    return PascalLanguageServer

case self.DELPHI:
    from solidlsp.language_servers.delphi_server import DelphiLanguageServer
    return DelphiLanguageServer
```

#### 2.2 `pyproject.toml` 修改

**添加的 pytest 标记**:
```toml
"pascal: language server running for Pascal/Free Pascal",
"delphi: language server running for Delphi",
```

### 3. 测试项目和测试用例

#### 3.1 测试项目结构

**目录**: `test/resources/repos/pascal/test_repo/`

```
test_repo/
├── main.pas          # 主程序文件
│   ├── TUser 类 (带构造函数、析构函数、方法、属性)
│   ├── TUserManager 类 (用户管理)
│   ├── CalculateSum 函数
│   └── PrintMessage 过程
├── lib/
│   └── helper.pas    # 辅助单元
│       ├── THelper 类 (类方法)
│       ├── GetHelperMessage 函数
│       ├── MultiplyNumbers 函数
│       └── LogMessage 过程
└── .gitignore
```

**测试覆盖的 Pascal 特性**:
- 类定义和继承
- 构造函数和析构函数
- 方法和属性
- 单元引用 (uses)
- 函数和过程
- 类型定义

#### 3.2 测试用例

**文件路径**: `test/solidlsp/pascal/test_pascal_basic.py`

**测试内容**:
1. `test_pascal_language_server_initialization`: 测试 LSP 初始化
2. `test_pascal_request_document_symbols`: 测试符号检测
3. `test_pascal_class_methods`: 测试类方法检测
4. `test_pascal_helper_unit_symbols`: 测试跨文件符号
5. `test_pascal_properties`: 测试属性检测
6. `test_pascal_cross_file_references`: 测试跨文件引用

## 使用方法

### 在项目中启用 Pascal/Delphi 支持

在项目根目录创建 `project.yml` 文件:

```yaml
# 仅使用 Pascal
languages:
  - pascal

# 或仅使用 Delphi
languages:
  - delphi

# 或同时使用两者（适用于混合项目）
languages:
  - pascal
  - delphi
  - python  # 可以同时支持多种语言
```

### 环境配置

#### Pascal (FPC) 环境变量 (可选)

```bash
export FPCDIR=/usr/lib/fpc/3.2.2
export LAZARUSDIR=/usr/share/lazarus
```

#### Delphi 环境变量 (可选)

```bash
export BDS="C:\Program Files (x86)\Embarcadero\Studio\23.0"
```

### 在 Claude Code 中使用

启用 Serena 后，Claude Code 可以使用以下符号级操作:

```python
# 查找 Pascal 类定义
find_symbol("TUser")

# 查找方法的所有引用
find_referencing_symbols("TUser.GetInfo")

# 在指定方法后插入代码
insert_after_symbol("TUser.UpdateAge", new_code)
```

## 运行测试

### 运行 Pascal 测试

```bash
# 运行所有 Pascal 测试
pytest test/solidlsp/pascal -v -m pascal

# 运行特定测试
pytest test/solidlsp/pascal/test_pascal_basic.py::TestPascalLanguageServerBasics::test_pascal_request_document_symbols -v
```

### 运行前准备

1. **Pascal 测试前准备**:
   ```bash
   # 确保已安装 FPC 和 Lazarus
   fpc -version
   lazbuild --version
   ```

2. **Delphi 测试前准备**:
   ```bash
   # 确保 RAD Studio 已安装且 DelphiLSP.exe 可用
   where DelphiLSP.exe
   ```

## 已知限制

### Pascal (pasls)

1. **首次运行较慢**: 如果 pasls 未安装，首次运行会自动编译，可能需要几分钟
2. **依赖要求**: 需要完整的 Lazarus 安装来编译 pasls
3. **平台限制**: pasls 在 Windows 上运行良好，Linux/macOS 需要确保依赖正确安装

### Delphi (DelphiLSP)

1. **商业软件依赖**: 需要购买 RAD Studio 11.0 或更高版本
2. **仅 Windows**: DelphiLSP 目前仅支持 Windows 平台
3. **初始化时间**: Controller 模式启动多个 agent 进程，初始化可能需要 10 秒左右

## 文件清单

### 新增文件

```
src/solidlsp/language_servers/
├── pascal_server.py                           # Pascal LSP 实现
└── delphi_server.py                           # Delphi LSP 实现

test/solidlsp/pascal/
└── test_pascal_basic.py                       # Pascal 测试用例

test/resources/repos/pascal/test_repo/
├── main.pas                                   # 测试主程序
├── lib/helper.pas                             # 测试辅助单元
└── .gitignore                                 # Git 忽略配置
```

### 修改文件

```
src/solidlsp/ls_config.py                      # 添加语言枚举和配置
pyproject.toml                                 # 添加 pytest 标记
```

## 下一步工作

### 必需 (提交 PR 前)

- [ ] 在实际环境中运行测试验证功能
- [ ] 更新 `README.md` 添加 Pascal 和 Delphi 到支持的语言列表
- [ ] 更新 `CHANGELOG.md` 记录本次更新
- [ ] 添加语言特定的文档 (如果需要)
- [ ] 创建示例项目展示用法

### 可选 (后续改进)

- [ ] 添加 Delphi 的测试项目和测试用例
- [ ] 优化 pasls 的安装流程 (提供预编译二进制)
- [ ] 添加更多 Pascal 方言支持 (Object Pascal, Turbo Pascal)
- [ ] 改进错误诊断和提示信息
- [ ] 添加代码格式化支持 (JCF - Jedi Code Formatter)

## 参考资料

### Pascal Language Server (pasls)
- GitHub: https://github.com/genericptr/pascal-language-server
- VS Code 扩展: https://github.com/genericptr/pasls-vscode

### DelphiLSP
- 官方文档: https://docwiki.embarcadero.com/RADStudio/Alexandria/en/Using_DelphiLSP_Code_Insight_with_Other_Editors
- RAD Studio: https://www.embarcadero.com/products/rad-studio

### Serena 开发指南
- 添加新语言支持: `.serena/memories/adding_new_language_support_guide.md`
- 贡献指南: `CONTRIBUTING.md`

## 作者

实现者: Claude Code (AI Assistant)
实现日期: 2025-12-16
项目: Serena Coding Agent Toolkit
