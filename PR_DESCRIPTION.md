# Add Terraform Language Server Support to Serena

## 🚀 Overview

This PR adds comprehensive Terraform language server support to Serena, enabling powerful infrastructure-as-code analysis capabilities. Users can now use all of Serena's tools (`find_symbol`, `find_referencing_symbols`, `get_symbols_overview`, `search_for_pattern`, etc.) on their Terraform projects.

## ✨ Features Added

### Core Language Support
- ✅ Added `TERRAFORM` to the `Language` enum
- ✅ File pattern matching for `.tf`, `.tfvars`, and `.tfstate` files
- ✅ Integration with HashiCorp's `terraform-ls` language server

### Language Server Implementation
- ✅ Complete `TerraformLS` class with LSP protocol handling
- ✅ Automatic dependency checking for `terraform` and `terraform-ls`
- ✅ Proper directory ignoring (`.terraform`, `terraform.tfstate.d`, etc.)
- ✅ Factory integration for automatic instantiation

### Test Infrastructure
- ✅ Comprehensive test suite covering all major functionality
- ✅ Sample Terraform project with real-world examples
- ✅ Tests for resource references, variable tracking, and pattern searching

## 🎯 Use Cases Enabled

### Infrastructure Auditing
```bash
# Find all S3 buckets in your project
serena find_symbol "aws_s3_bucket"

# Find all references to a specific bucket
serena find_referencing_symbols "aws_s3_bucket.app_bucket"
```

### Variable Management
```bash
# Find all variable definitions
serena search_for_pattern "variable\s+\"[^\"]+\""

# Find where a variable is used
serena find_referencing_symbols "var.instance_type"
```

### Resource Relationships
```bash
# Find all resources that reference a VPC
serena find_referencing_symbols "aws_vpc.main"

# Get overview of all resources in a module
serena get_symbols_overview "modules/networking"
```

### Security Analysis
```bash
# Find security groups with open access
serena search_for_pattern "cidr_blocks.*=.*\"0\.0\.0\.0/0\""

# Find all IAM policies
serena find_symbol "aws_iam_policy"
```

## 📁 Files Added/Modified

### Core Implementation
- `src/solidlsp/ls_config.py` - Added TERRAFORM enum and file patterns
- `src/solidlsp/ls.py` - Added factory integration
- `src/solidlsp/language_servers/terraform_ls/` - Complete language server implementation
  - `terraform_ls.py` - Main implementation
  - `initialize_params.json` - LSP initialization parameters
  - `runtime_dependencies.json` - Binary download configuration

### Test Infrastructure
- `test/solidlsp/terraform/test_terraform_basic.py` - Comprehensive test suite
- `test/resources/repos/terraform/test_repo/` - Sample Terraform project
  - `main.tf` - Infrastructure configuration (VPC, EC2, S3, Security Groups)
  - `variables.tf` - Input variables with validation
  - `outputs.tf` - Output values
  - `data.tf` - Data sources

### Documentation
- `TERRAFORM_IMPLEMENTATION_SUMMARY.md` - Complete implementation guide

## 🔧 Dependencies

### Required Tools
- **terraform** - The Terraform CLI tool
- **terraform-ls** - HashiCorp's Terraform Language Server

### Installation
```bash
# Install terraform (if not already installed)
brew install terraform

# Install terraform-ls
brew install hashicorp/tap/terraform-ls
```

## ✅ Testing

### Verification Commands
```bash
# Check if Terraform support is available
uv run python -c "from solidlsp.ls_config import Language; print('terraform' in [lang.value for lang in Language])"

# Test language server creation
uv run python -c "
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls import SolidLanguageServer

config = LanguageServerConfig(code_language=Language.TERRAFORM)
logger = LanguageServerLogger()
ls = SolidLanguageServer.create(config, logger, 'test/resources/repos/terraform/test_repo')
print('✓ Terraform language server created successfully')
"
```

### Running Tests
```bash
# Run Terraform-specific tests
uv run pytest test/solidlsp/terraform/ -v
```

## 🌟 Integration with Popular Terraform Modules

This implementation supports analysis of popular Terraform modules:

### terraform-aws-vpc
- Find subnet references: `find_referencing_symbols "module.vpc.private_subnets"`
- Analyze VPC structure: `get_symbols_overview "modules/vpc"`

### terraform-aws-iam
- Audit IAM roles: `find_symbol "aws_iam_role"`
- Find policy attachments: `find_referencing_symbols "aws_iam_policy.s3_read_policy"`

### terraform-aws-s3-bucket
- Inventory buckets: `find_symbol "aws_s3_bucket"`
- Find bucket references: `find_referencing_symbols "module.s3_bucket.arn"`

## 🧪 How to Test

1. **Clone a real Terraform project** (e.g., `terraform-aws-modules/terraform-aws-vpc`)
2. **Activate the project** in Serena with `activate_project`
3. **Use Serena's tools** to analyze the infrastructure:
   - `get_symbols_overview "."` - Get project overview
   - `find_symbol "aws_vpc"` - Find all VPC resources
   - `find_referencing_symbols "cidr"` - Find variable usage
   - `search_for_pattern "Name\\s*="` - Find all Name tags

## 📊 Impact

This addition significantly expands Serena's capabilities to include infrastructure-as-code analysis, making it a powerful tool for:
- DevOps engineers managing Terraform infrastructure
- Security teams auditing cloud resources
- Platform teams standardizing infrastructure patterns
- Developers understanding complex infrastructure dependencies

## 🔍 Review Notes

- All changes follow existing Serena patterns and conventions
- Implementation is based on proven patterns from other language servers (Go, Python, etc.)
- Comprehensive test coverage ensures reliability
- Documentation provides clear usage examples and installation instructions

---

**Ready for review and testing!** 🎉
