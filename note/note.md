# Phân Tích Project Serena - Coding Agent Toolkit

## Mục Lục
1. [Tổng Quan](#tổng-quan)
2. [Chức Năng Chính](#chức-năng-chính)
3. [Kiến Trúc Hệ Thống](#kiến-trúc-hệ-thống)
4. [Hướng Dẫn Sử Dụng](#hướng-dẫn-sử-dụng)
5. [Các Công Cụ (Tools) Có Sẵn](#các-công-cụ-tools-có-sẵn)
6. [Lợi Ích & Use Cases](#lợi-ích--use-cases)
7. [Ví Dụ Thực Tế](#ví-dụ-thực-tế)

---

## Tổng Quan

### Serena là gì?

**Serena** là một **bộ công cụ coding agent mạnh mẽ** (coding agent toolkit) cho phép biến các mô hình ngôn ngữ lớn (LLM) như Claude, GPT, Gemini thành một agent lập trình đầy đủ tính năng, có khả năng làm việc **trực tiếp trên codebase** của bạn.

### Đặc Điểm Nổi Bật

- 🚀 **Miễn phí & mã nguồn mở** (MIT License)
- 🔧 **Cung cấp công cụ semantic code retrieval và editing** giống như IDE
- 🌐 **Không phụ thuộc vào LLM cụ thể** - tích hợp được với nhiều LLM khác nhau
- 🔌 **Không bị ràng buộc vào framework** - dễ dàng tích hợp
- 🌍 **Hỗ trợ 30+ ngôn ngữ lập trình**

### Serena Giải Quyết Vấn Đề Gì?

Khi làm việc với coding agents thông thường, LLM thường phải:
- ❌ Đọc **toàn bộ file** để tìm một function
- ❌ Sử dụng **grep/search đơn giản** để tìm code
- ❌ Thực hiện **string replacement cơ bản** không an toàn

Với Serena, LLM có thể:
- ✅ Sử dụng **code-centric tools** như `find_symbol`, `find_referencing_symbols`
- ✅ Thực hiện **symbolic editing** chính xác với `insert_after_symbol`, `replace_symbol_body`
- ✅ **Refactoring an toàn** với `rename_symbol` sử dụng LSP
- ✅ Làm việc **hiệu quả** với codebase lớn và phức tạp

---

## Chức Năng Chính

### 1. Phân Tích Code Ngữ Nghĩa (Semantic Code Analysis)

Serena sử dụng **Language Server Protocol (LSP)** để:
- Hiểu cấu trúc code theo **symbols** (class, function, variable, method)
- Phát hiện **quan hệ giữa các symbols** (references, definitions, implementations)
- Thực hiện **refactoring an toàn** (rename, extract, reorganize)
- Hoạt động như một **developer có kinh nghiệm sử dụng IDE**

### 2. Hệ Thống Memory (Trí Nhớ Dự Án)

Serena có khả năng:
- **Lưu trữ kiến thức** về project trong `.serena/memories/`
- **Onboarding tự động**: Tự động tìm hiểu cấu trúc, cách build/test project
- **Persistent knowledge**: Kiến thức được lưu giữ qua các sessions
- **Contextual retrieval**: Truy xuất kiến thức dựa trên relevance

### 3. Hỗ Trợ Đa Ngôn Ngữ (30+ Languages)

Danh sách ngôn ngữ được hỗ trợ:

**Ngôn ngữ phổ biến:**
- Python, TypeScript, JavaScript, Java, Go, Rust, C#, PHP, Ruby

**Statically typed:**
- Kotlin, Swift, Scala, Haskell, C/C++

**Functional programming:**
- Elixir, Erlang, Clojure, Elm

**Khác:**
- Bash, Perl, Lua, Nix, Dart, Fortran, R, Zig, Julia, AL, Markdown, Terraform

### 4. Tích Hợp LLM Linh Hoạt

Serena có thể tích hợp với LLM qua **3 cách**:

#### a) Model Context Protocol (MCP) - Phổ biến nhất
- **Desktop apps**: Claude Code, Claude Desktop
- **Terminal clients**: Codex, Gemini-CLI, Qwen3-Coder, rovodev, OpenHands CLI
- **IDEs**: VSCode, Cursor, IntelliJ
- **Extensions**: Cline, Roo Code
- **Local clients**: OpenWebUI, Jan, Agno

#### b) OpenAPI (qua mcpo)
- Cho ChatGPT và các client không hỗ trợ MCP

#### c) Custom Integration
- Tích hợp trực tiếp vào agent framework tùy chỉnh

---

## Kiến Trúc Hệ Thống

### Kiến Trúc Tổng Quan

```
┌─────────────────────────────────────────────────────────┐
│                   SerenaAgent                           │
│         (Central Orchestrator)                          │
│  - Quản lý projects, tools, user interactions           │
│  - Điều phối language servers & memory persistence      │
│  - Quản lý tool registry và configurations              │
└──────────────────────┬──────────────────────────────────┘
                       │
           ┌───────────┴────────────┐
           │                        │
┌──────────▼──────────┐  ┌──────────▼────────────┐
│ SolidLanguageServer │  │    Tool System         │
│  - LSP wrapper      │  │  ┌──────────────────┐  │
│  - Symbol operations│  │  │ file_tools       │  │
│  - Multi-language   │  │  │ symbol_tools     │  │
│  - Caching & error  │  │  │ memory_tools     │  │
│    recovery         │  │  │ config_tools     │  │
│                     │  │  │ workflow_tools   │  │
└─────────────────────┘  │  └──────────────────┘  │
                         └───────────────────────┘
```

### Core Components

#### 1. SerenaAgent (`src/serena/agent.py`)
- Orchestrator trung tâm quản lý toàn bộ hệ thống
- Điều phối language servers, memory persistence
- Quản lý tool registry và context/mode configurations

#### 2. SolidLanguageServer (`src/solidlsp/ls.py`)
- Wrapper thống nhất cho Language Server Protocol
- Cung cấp interface language-agnostic cho symbol operations
- Xử lý caching, error recovery, lifecycle của language servers

#### 3. Tool System (`src/serena/tools/`)
Hệ thống công cụ bao gồm:
- **file_tools.py**: File system operations, search, regex replacements
- **symbol_tools.py**: Language-aware symbol finding, navigation, editing
- **memory_tools.py**: Project knowledge persistence và retrieval
- **config_tools.py**: Project activation, mode switching
- **workflow_tools.py**: Onboarding và meta-operations

#### 4. Configuration System (`src/serena/config/`)
- **Contexts**: Định nghĩa tool sets cho các environments (desktop-app, agent, ide-assistant)
- **Modes**: Operational patterns (planning, editing, interactive, one-shot)
- **Projects**: Per-project settings và language server configs

### Luồng Hoạt Động

```
User Request
    ↓
┌───────────────────────────────────────┐
│  MCP Server Interface                 │
└───────────┬───────────────────────────┘
            ↓
┌───────────────────────────────────────┐
│  SerenaAgent (Tool Orchestration)     │
└───────┬───────────────────────────────┘
        │
        ├──→ Language Server (LSP) ──→ Symbol Analysis
        ├──→ Memory System ──→ Project Knowledge
        └──→ File System ──→ File Operations
                ↓
        Results to LLM
```

---

## Hướng Dẫn Sử Dụng

### Bước 1: Cài Đặt Prerequisites

#### Cài đặt `uv` (Python package manager)

**Linux/macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### Kiểm tra cài đặt:
```bash
uv --version
```

### Bước 2: Khởi Chạy MCP Server

#### Xem các options:
```bash
uvx --from git+https://github.com/oraios/serena serena start-mcp-server --help
```

#### Khởi chạy cơ bản:
```bash
uvx --from git+https://github.com/oraios/serena serena start-mcp-server
```

#### Khởi chạy với project cụ thể:
```bash
uvx --from git+https://github.com/oraios/serena serena start-mcp-server --project /path/to/your/project
```

### Bước 3: Cấu Hình MCP Client

#### 3.1. Claude Code (Web)

Thêm vào file cấu hình MCP của Claude Code:

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server"
      ]
    }
  }
}
```

#### 3.2. Claude Desktop

Chỉnh sửa file cấu hình (tùy OS):

**macOS:**
```bash
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```bash
%APPDATA%\Claude\claude_desktop_config.json
```

**Nội dung:**
```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server"
      ]
    }
  }
}
```

#### 3.3. VSCode với Cline/Roo Code

Tương tự, thêm cấu hình MCP server vào extension settings.

### Bước 4: Workflow Làm Việc với Project

#### 4.1. Tạo Project Mới

```bash
cd /path/to/your/project

# Tạo project với ngôn ngữ cụ thể
uvx --from git+https://github.com/oraios/serena serena project create --language python

# Tạo với tên tùy chỉnh
uvx --from git+https://github.com/oraios/serena serena project create --language python --name "My Awesome Project"

# Tạo và index ngay lập tức
uvx --from git+https://github.com/oraios/serena serena project create --language python --index

# Tạo project multi-language
uvx --from git+https://github.com/oraios/serena serena project create --language python --language typescript --language go
```

**Kết quả:**
- File `.serena/project.yml` được tạo với cấu hình project
- Có thể chỉnh sửa file này để tùy chỉnh settings

#### 4.2. Index Project (Khuyên dùng cho project lớn)

```bash
cd /path/to/your/project
uvx --from git+https://github.com/oraios/serena serena project index
```

**Lợi ích:**
- Giảm thời gian startup của MCP server
- Tăng tốc độ áp dụng tools lần đầu
- Tự động cập nhật khi files thay đổi

#### 4.3. Kích Hoạt Project

**Cách 1: Trong conversation với LLM**
```
"Activate the project /path/to/my_project"
```
hoặc
```
"Activate the project my_project"
```

**Cách 2: Khi khởi động MCP server**
```bash
serena start-mcp-server --project /path/to/my_project
```

#### 4.4. Onboarding (Tự động)

Khi project được activate lần đầu tiên, Serena sẽ tự động:
1. Phân tích cấu trúc project
2. Tìm hiểu cách build và test
3. Xác định entry points và important files
4. Tạo memories trong `.serena/memories/`

**Memories bao gồm:**
- `project_structure.md`: Cấu trúc tổng quan
- `build_and_test.md`: Cách build/test project
- `key_components.md`: Các components quan trọng
- Và các memories khác tùy project

**Lưu ý:**
- Onboarding có thể đọc nhiều file → fill context
- Khuyên nên switch sang conversation mới sau onboarding
- Có thể edit/thêm memories thủ công trong `.serena/memories/`

#### 4.5. Làm Việc với LLM

Sau khi setup xong, yêu cầu LLM thực hiện tasks:

**Ví dụ:**
```
"Find all functions that call the process_data function"

"Rename the User class to Customer throughout the codebase"

"Add error handling to the authenticate function"

"Explain how the authentication flow works in this project"

"Add a new method to the DatabaseManager class to handle batch inserts"
```

### Bước 5: Best Practices

#### 5.1. Chuẩn Bị Codebase

✅ **Cấu trúc code tốt**: Serena hoạt động tốt với well-structured code

✅ **Type annotations**: Đặc biệt quan trọng cho dynamic languages (Python, JavaScript)

✅ **Clean git state**: Bắt đầu từ clean state để dễ inspect changes

#### 5.2. Git Configuration (Quan trọng trên Windows)

```bash
# Trên Windows, enable autocrlf
git config --global core.autocrlf true
```

Điều này tránh huge diffs do line endings.

#### 5.3. Testing & Linting

✅ Có **automated tests** với coverage tốt

✅ Có **linting** để check code style

✅ Bắt đầu từ state **all tests pass**

Serena sẽ sử dụng test/lint results để assess correctness.

---

## Các Công Cụ (Tools) Có Sẵn

### 1. Symbol Tools (Công cụ làm việc với symbols)

#### `find_symbol`
Tìm symbols (class, function, variable) theo tên.

**Parameters:**
- `name`: Tên hoặc substring của symbol
- `type` (optional): Lọc theo loại (class, function, method, variable, etc.)
- `local` (optional): Tìm trong file cụ thể hoặc toàn project

**Ví dụ:**
```
find_symbol(name="User", type="class")
find_symbol(name="process", local="src/main.py")
```

#### `find_referencing_symbols`
Tìm nơi sử dụng một symbol.

**Parameters:**
- `file_path`: Đường dẫn file chứa symbol
- `line`: Dòng của symbol
- `type` (optional): Lọc theo loại reference

**Ví dụ:**
```
find_referencing_symbols(file_path="src/models.py", line=15)
```

#### `get_symbols_overview`
Xem tổng quan các symbols trong file.

**Parameters:**
- `file_path`: Đường dẫn file

**Ví dụ:**
```
get_symbols_overview(file_path="src/database.py")
```

#### `rename_symbol`
Đổi tên symbol trong toàn bộ codebase (sử dụng LSP refactoring).

**Parameters:**
- `file_path`: File chứa symbol
- `line`: Dòng của symbol
- `new_name`: Tên mới

**Ví dụ:**
```
rename_symbol(file_path="src/models.py", line=10, new_name="Customer")
```

### 2. Symbol Editing Tools

#### `insert_after_symbol`
Chèn code sau định nghĩa của symbol.

**Parameters:**
- `file_path`: File chứa symbol
- `symbol_name`: Tên symbol
- `content`: Nội dung cần chèn

#### `insert_before_symbol`
Chèn code trước định nghĩa của symbol.

#### `replace_symbol_body`
Thay thế toàn bộ nội dung của symbol.

**Parameters:**
- `file_path`: File chứa symbol
- `symbol_name`: Tên symbol
- `new_content`: Nội dung mới

### 3. File Tools

#### `read_file`
Đọc nội dung file.

#### `create_text_file`
Tạo hoặc ghi đè file.

#### `find_file`
Tìm files theo đường dẫn relative.

#### `list_dir`
List files và directories (có thể recursive).

#### `search_for_pattern`
Tìm kiếm pattern trong project (như grep).

#### `replace_regex`
Thay thế content sử dụng regex.

### 4. Line-based Editing Tools

#### `delete_lines`
Xóa một range của lines.

**Parameters:**
- `file_path`: File path
- `start_line`: Dòng bắt đầu
- `end_line`: Dòng kết thúc

#### `replace_lines`
Thay thế một range của lines.

**Parameters:**
- `file_path`: File path
- `start_line`: Dòng bắt đầu
- `end_line`: Dòng kết thúc
- `new_content`: Nội dung mới

#### `insert_at_line`
Chèn content tại một dòng cụ thể.

### 5. Memory Tools

#### `write_memory`
Lưu kiến thức về project.

**Parameters:**
- `name`: Tên memory (sẽ tạo file `.serena/memories/{name}.md`)
- `content`: Nội dung markdown

**Ví dụ:**
```
write_memory(
  name="authentication_flow",
  content="# Authentication Flow\n\n1. User submits credentials..."
)
```

#### `read_memory`
Đọc memory đã lưu.

**Parameters:**
- `name`: Tên memory

#### `list_memories`
Xem danh sách các memories có sẵn.

#### `delete_memory`
Xóa memory.

### 6. Project & Config Tools

#### `activate_project`
Kích hoạt project.

**Parameters:**
- `project_path_or_name`: Đường dẫn hoặc tên project

#### `get_current_config`
Xem cấu hình hiện tại (projects, tools, contexts, modes).

#### `switch_modes`
Chuyển đổi operation modes.

**Modes:**
- `planning`: Mode lập kế hoạch
- `editing`: Mode chỉnh sửa code
- `interactive`: Mode tương tác
- `one-shot`: Mode one-shot tasks

#### `remove_project`
Xóa project khỏi configuration.

### 7. Workflow Tools

#### `onboarding`
Thực hiện onboarding cho project (thường tự động).

#### `check_onboarding_performed`
Kiểm tra xem onboarding đã được thực hiện chưa.

#### `prepare_for_new_conversation`
Cung cấp instructions để chuẩn bị cho conversation mới.

#### `summarize_changes`
Tổng kết các thay đổi đã thực hiện.

### 8. Thinking Tools

#### `think_about_collected_information`
Tool để suy nghĩ về tính đầy đủ của thông tin đã thu thập.

#### `think_about_task_adherence`
Kiểm tra xem agent có còn on-track với task không.

#### `think_about_whether_you_are_done`
Xác định xem task đã hoàn thành thật sự chưa.

### 9. Other Tools

#### `execute_shell_command`
Thực thi shell command.

**Lưu ý:** Cẩn thận với tool này, có thể ảnh hưởng hệ thống.

#### `restart_language_server`
Restart language server (cần thiết khi có edits ngoài Serena).

---

## Lợi Ích & Use Cases

### Lợi Ích Chính

#### 1. Hiệu Quả Token (Token Efficiency)
- ✅ Không cần đọc toàn bộ file
- ✅ Chỉ đọc symbols cần thiết
- ✅ Giảm context usage → giảm chi phí API
- ✅ Nhanh hơn trong việc tìm kiếm code

**Ví dụ:**
- Thay vì đọc 5000 dòng code để tìm 1 function
- Chỉ cần `find_symbol()` và đọc symbol đó (10-50 dòng)

#### 2. Chính Xác Hơn (Precision)
- ✅ Sử dụng LSP → hiểu code đúng ngữ nghĩa
- ✅ Không phải text matching đơn thuần
- ✅ Phát hiện được references, implementations
- ✅ Refactoring an toàn

**Ví dụ:**
- Rename `user` variable không làm thay đổi `user` trong string
- Tìm được overridden methods, interface implementations

#### 3. An Toàn Hơn (Safety)
- ✅ Refactoring được kiểm tra bởi language server
- ✅ Type-aware editing
- ✅ Tránh breaking changes

#### 4. Làm Việc với Codebase Lớn
- ✅ Không bị giới hạn bởi context window
- ✅ Navigate hiệu quả trong complex projects
- ✅ Index + cache → performance tốt

#### 5. Chất Lượng Code Tốt Hơn
- ✅ Hiểu cấu trúc → sinh code structured hơn
- ✅ Follow existing patterns
- ✅ Maintain consistency

### Use Cases Lý Tưởng

#### 1. Refactoring Code
**Tasks:**
- Rename classes, functions, variables
- Extract methods/functions
- Reorganize code structure
- Split large files

**Ví dụ:**
```
"Rename the User class to Customer and update all references"
"Extract the validation logic into a separate function"
"Move the authentication logic to a separate module"
```

#### 2. Bug Fixing
**Tasks:**
- Tìm nơi function được gọi
- Trace code flow
- Tìm root cause
- Fix và verify

**Ví dụ:**
```
"Find all places where calculate_discount is called and check for edge cases"
"Trace the flow of data from user input to database"
```

#### 3. Feature Development
**Tasks:**
- Thêm methods vào existing classes
- Extend functionality
- Integrate với existing code
- Follow existing patterns

**Ví dụ:**
```
"Add a method to handle bulk user creation in the UserManager class"
"Implement caching for the product search feature"
```

#### 4. Code Review & Understanding
**Tasks:**
- Phân tích code structure
- Tìm dependencies
- Document code
- Onboarding vào codebase mới

**Ví dụ:**
```
"Explain how the payment processing workflow works"
"Find all classes that depend on the Database class"
"Document the API authentication mechanism"
```

#### 5. Migration & Updates
**Tasks:**
- Update API calls
- Migrate to new libraries
- Update deprecated code

**Ví dụ:**
```
"Update all database queries to use the new ORM syntax"
"Replace all uses of the old logger with the new logging framework"
```

### Khi KHÔNG Nên Dùng Serena

❌ **Project rất nhỏ (1-3 files)**
- Overhead không đáng
- File-based tools đơn giản là đủ

❌ **Viết code hoàn toàn mới từ đầu**
- Serena tối ưu cho codebase có sẵn
- Chưa có structure để exploit

❌ **Tasks rất đơn giản**
- String replacement đơn thuần
- Đọc 1-2 files nhỏ
- Không cần LSP

❌ **Unstructured code**
- "God classes" với enormous functions
- Code không modular
- Serena cần structure để hoạt động tốt

---

## Ví Dụ Thực Tế

### Ví dụ 1: Tìm và Sửa Bug Null Pointer

**Scenario:** Có bug null pointer khi xử lý user data.

**Workflow:**

```
User: "Find where the process_user_data function is called and check for potential null pointer errors"

AI với Serena:
1. find_symbol(name="process_user_data", type="function")
   → Tìm thấy ở src/services/user_service.py:45

2. read_file(file_path="src/services/user_service.py", start_line=45, end_line=70)
   → Đọc function definition

3. find_referencing_symbols(file_path="src/services/user_service.py", line=45)
   → Tìm thấy 3 nơi gọi:
   - src/api/user_api.py:120
   - src/workers/user_worker.py:55
   - src/tasks/sync_task.py:88

4. read_file() cho mỗi location
   → Phát hiện user_worker.py:55 không check null

5. insert_before_symbol() hoặc replace_lines()
   → Thêm null check

6. write_memory(name="bug_fix_user_data", content="Fixed null pointer...")
   → Lưu lại kiến thức
```

### Ví dụ 2: Refactoring - Rename Class

**Scenario:** Đổi tên class `User` thành `Customer` trong toàn bộ codebase.

**Workflow:**

```
User: "Rename the User class to Customer throughout the codebase"

AI với Serena:
1. find_symbol(name="User", type="class")
   → Tìm thấy ở src/models/user.py:10

2. rename_symbol(
     file_path="src/models/user.py",
     line=10,
     new_name="Customer"
   )
   → LSP tự động rename:
   - Class definition
   - All imports
   - All type hints
   - All instantiations
   - All references

3. execute_shell_command("git diff")
   → Verify changes
```

**Kết quả:** An toàn, chính xác, không miss bất kỳ reference nào.

### Ví dụ 3: Onboarding Project Mới

**Scenario:** Mới join project, cần hiểu codebase.

**Workflow:**

```
User: "Help me understand this project structure and how authentication works"

AI với Serena:
1. onboarding()
   → Tự động phân tích:
   - Project structure (directories, main files)
   - Build & test commands
   - Entry points
   - Dependencies
   → Tạo memories

2. search_for_pattern(pattern="authenticate")
   → Tìm thấy authentication-related files

3. find_symbol(name="authenticate", type="function")
   → Tìm main authentication function

4. get_symbols_overview(file_path="src/auth/authenticator.py")
   → Xem tất cả classes/functions trong auth module

5. find_referencing_symbols()
   → Trace authentication flow

6. write_memory(
     name="authentication_flow",
     content="# Authentication Flow\n\n## Overview\n..."
   )
   → Lưu lại hiểu biết
```

### Ví dụ 4: Thêm Feature Mới

**Scenario:** Thêm batch processing capability vào existing service.

**Workflow:**

```
User: "Add a batch_process method to the DataProcessor class that can handle multiple items at once"

AI với Serena:
1. find_symbol(name="DataProcessor", type="class")
   → Tìm thấy ở src/processors/data_processor.py:25

2. get_symbols_overview(file_path="src/processors/data_processor.py")
   → Xem các methods hiện có:
   - process_single(item)
   - validate(item)
   - _format_output(result)

3. read_file() để hiểu implementation details

4. insert_after_symbol(
     file_path="src/processors/data_processor.py",
     symbol_name="process_single",
     content="""
     def batch_process(self, items: List[Any]) -> List[Result]:
         \"\"\"Process multiple items in batch.\"\"\"
         results = []
         for item in items:
             results.append(self.process_single(item))
         return results
     """
   )

5. execute_shell_command("uv run poe test")
   → Run tests để verify
```

### Ví dụ 5: Code Review - Tìm Dependencies

**Scenario:** Cần refactor Database class, muốn biết impact.

**Workflow:**

```
User: "Find all classes that depend on the Database class so I know what will be affected by my refactoring"

AI với Serena:
1. find_symbol(name="Database", type="class")
   → Tìm thấy ở src/core/database.py:15

2. find_referencing_symbols(
     file_path="src/core/database.py",
     line=15
   )
   → Tìm thấy references trong:
   - src/repositories/user_repository.py
   - src/repositories/product_repository.py
   - src/services/cache_service.py
   - src/api/main.py
   - test/test_database.py

3. Đọc mỗi file để analyze dependency type

4. write_memory(
     name="database_dependencies",
     content="# Database Class Dependencies\n\n..."
   )
   → Document findings
```

---

## Development Commands (Cho Contributors)

Nếu bạn đang phát triển Serena:

### Format Code
```bash
uv run poe format
```
Chạy BLACK + RUFF để format code.

### Type Checking
```bash
uv run poe type-check
```
Chạy mypy để check types.

### Run Tests
```bash
# Default tests (exclude java/rust/erlang)
uv run poe test

# Test specific languages
uv run poe test -m "python or go"
uv run poe test -m "typescript"

# Run all tests including slow ones
uv run poe test -m ""
```

### Linting
```bash
uv run poe lint
```
Check code style without fixing.

### Build Documentation
```bash
uv run poe doc-build
```

---

## Configuration System

### Configuration Hierarchy

Configuration được load theo thứ tự ưu tiên:

1. **Command-line arguments**
   ```bash
   serena start-mcp-server --project /path --context ide-assistant
   ```

2. **Project-specific config** (`.serena/project.yml`)
   ```yaml
   name: My Project
   languages:
     - python
     - typescript
   ```

3. **User config** (`~/.serena/serena_config.yml`)
   ```yaml
   default_context: agent
   ```

4. **Active modes và contexts**

### Contexts

Contexts định nghĩa tool sets cho các environments:

- **desktop-app**: Cho desktop applications như Claude Desktop
- **agent**: Cho autonomous agents
- **ide-assistant**: Cho IDE integrations

### Modes

Modes định nghĩa operational patterns:

- **planning**: Lập kế hoạch trước khi code
- **editing**: Focus vào editing code
- **interactive**: Tương tác với user nhiều hơn
- **one-shot**: Xử lý single tasks

---

## Tài Nguyên & Links

### Documentation
- **User Guide**: https://oraios.github.io/serena/02-usage/000_intro.html
- **Tool List**: https://oraios.github.io/serena/01-about/035_tools.html
- **Language Support**: https://oraios.github.io/serena/01-about/020_programming-languages.html

### Repository
- **GitHub**: https://github.com/oraios/serena
- **Issues**: https://github.com/oraios/serena/issues
- **Contributing**: https://github.com/oraios/serena/CONTRIBUTING.md

### Community
- **Reddit discussions**: r/ClaudeAI, r/ClaudeCode
- **YouTube reviews**: Xem demos và tutorials

### Blog Posts
- Serena's Design Principles
- Turning Claude Code into a Development Powerhouse
- Deconstructing Serena's MCP-powered Semantic Code Understanding Architecture

---

## Tổng Kết

**Serena** là một công cụ mạnh mẽ biến LLM thành một "developer với IDE", cung cấp:

✅ **Semantic code understanding** - Hiểu code theo ngữ nghĩa, không chỉ text

✅ **Precise editing** - Chỉnh sửa code chính xác và an toàn với LSP

✅ **Efficient navigation** - Navigate codebase lớn hiệu quả

✅ **Memory system** - Lưu trữ và tái sử dụng kiến thức về project

✅ **Multi-language support** - 30+ ngôn ngữ lập trình

✅ **Flexible integration** - Tích hợp với nhiều LLMs và clients

✅ **Cost-effective** - Giảm token usage → giảm chi phí

✅ **Open-source & free** - MIT License, miễn phí hoàn toàn

### Khi Nào Nên Dùng Serena?

- ✅ Codebase lớn và phức tạp
- ✅ Cần refactoring
- ✅ Cần hiểu code structure
- ✅ Bug fixing với code tracing
- ✅ Feature development trong existing code
- ✅ Code review và documentation

### Khi Nào KHÔNG Cần Serena?

- ❌ Project rất nhỏ (1-3 files)
- ❌ Viết code mới từ đầu
- ❌ Tasks đơn giản (string replacement)
- ❌ Unstructured code

---

**License**: MIT
**Version**: 0.1.4
**Python**: 3.11
**Maintained by**: Oraios AI (https://oraios-ai.de/)
