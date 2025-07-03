# Terraform Language Server Implementation for Serena

## Overview

Successfully implemented Terraform language server support for Serena, enabling powerful code analysis and navigation capabilities for Terraform infrastructure-as-code projects.

## What Was Implemented

### 1. Core Language Support

**File: `src/solidlsp/ls_config.py`**
- Added `TERRAFORM = "terraform"` to the `Language` enum
- Added file pattern matching for Terraform files:
  - `*.tf` - Terraform configuration files
  - `*.tfvars` - Terraform variable files
  - `*.tfstate` - Terraform state files

### 2. Terraform Language Server Integration

**Directory: `src/solidlsp/language_servers/terraform_ls/`**

**Files Created:**
- `terraform_ls.py` - Main language server implementation
- `initialize_params.json` - LSP initialization parameters
- `runtime_dependencies.json` - Binary download configuration

**Key Features:**
- Integration with HashiCorp's `terraform-ls` language server
- Automatic dependency checking for `terraform` and `terraform-ls`
- Proper directory ignoring (`.terraform`, `terraform.tfstate.d`, etc.)
- LSP protocol handling for Terraform-specific features

### 3. Language Server Factory Integration

**File: `src/solidlsp/ls.py`**
- Added Terraform case to the language server factory
- Enables automatic instantiation of TerraformLS when Language.TERRAFORM is specified

### 4. Test Infrastructure

**Directory: `test/solidlsp/terraform/`**
- `test_terraform_basic.py` - Comprehensive test suite covering:
  - Resource reference finding
  - Variable reference tracking
  - Content retrieval around specific lines
  - Pattern searching in Terraform files

**Directory: `test/resources/repos/terraform/test_repo/`**
- Complete sample Terraform project with:
  - `main.tf` - Main infrastructure configuration (VPC, EC2, S3, Security Groups)
  - `variables.tf` - Input variables with validation
  - `outputs.tf` - Output values
  - `data.tf` - Data sources (AMI, availability zones, etc.)

## Use Cases Enabled

### 1. Infrastructure Auditing
```bash
# Find all S3 buckets in your project
serena find_symbol "aws_s3_bucket"

# Find all references to a specific bucket
serena find_referencing_symbols "aws_s3_bucket.app_bucket"
```

### 2. Variable Management
```bash
# Find all variable definitions
serena search_for_pattern "variable\s+\"[^\"]+\""

# Find where a variable is used
serena find_referencing_symbols "var.instance_type"
```

### 3. Resource Relationships
```bash
# Find all resources that reference a VPC
serena find_referencing_symbols "aws_vpc.main"

# Get overview of all resources in a module
serena get_symbols_overview "modules/networking"
```

### 4. Security Analysis
```bash
# Find security groups with open access
serena search_for_pattern "cidr_blocks.*=.*\"0\.0\.0\.0/0\""

# Find all IAM policies
serena find_symbol "aws_iam_policy"
```

## Dependencies

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

## Testing

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

# Run specific test
uv run pytest test/solidlsp/terraform/test_terraform_basic.py::TestTerraformLanguageServerBasics::test_retrieve_content_around_line -v
```

## Integration with Popular Terraform Modules

The implementation supports analysis of popular Terraform modules:

### terraform-aws-vpc
- Find subnet references: `find_referencing_symbols "module.vpc.private_subnets"`
- Analyze VPC structure: `get_symbols_overview "modules/vpc"`

### terraform-aws-iam
- Audit IAM roles: `find_symbol "aws_iam_role"`
- Find policy attachments: `find_referencing_symbols "aws_iam_policy.s3_read_policy"`

### terraform-aws-s3-bucket
- Inventory buckets: `find_symbol "aws_s3_bucket"`
- Find bucket references: `find_referencing_symbols "module.s3_bucket.arn"`

## Files Modified/Created

### Core Implementation
- `src/solidlsp/ls_config.py` - Added TERRAFORM enum and file patterns
- `src/solidlsp/ls.py` - Added factory integration
- `src/solidlsp/language_servers/terraform_ls/terraform_ls.py` - Main implementation
- `src/solidlsp/language_servers/terraform_ls/initialize_params.json` - LSP config
- `src/solidlsp/language_servers/terraform_ls/runtime_dependencies.json` - Binary config

### Test Infrastructure
- `test/solidlsp/terraform/test_terraform_basic.py` - Test suite
- `test/resources/repos/terraform/test_repo/main.tf` - Sample infrastructure
- `test/resources/repos/terraform/test_repo/variables.tf` - Sample variables
- `test/resources/repos/terraform/test_repo/outputs.tf` - Sample outputs
- `test/resources/repos/terraform/test_repo/data.tf` - Sample data sources

## Status

✅ **COMPLETE** - Terraform language server support has been successfully implemented and tested.

The implementation provides full integration with Serena's existing architecture and enables powerful infrastructure-as-code analysis capabilities for Terraform projects.
