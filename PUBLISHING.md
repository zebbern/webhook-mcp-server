# Publishing to PyPI Guide

This guide provides step-by-step instructions for publishing the `webhook-mcp-server` package to the Python Package Index (PyPI).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Preparation](#preparation)
- [Building the Package](#building-the-package)
- [Publishing to PyPI](#publishing-to-pypi)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Version Management](#version-management)

## Prerequisites

Before publishing to PyPI, ensure you have the following:

### 1. PyPI Account

- **Production PyPI**: Create an account at [https://pypi.org/account/register/](https://pypi.org/account/register/)
- **Test PyPI** (recommended for first-time testing): Create an account at [https://test.pypi.org/account/register/](https://test.pypi.org/account/register/)

### 2. API Token

For secure authentication, create an API token:

1. Log in to your PyPI account
2. Navigate to Account Settings → API tokens
3. Click "Add API token"
4. Give it a descriptive name (e.g., "webhook-mcp-server-upload")
5. Set the scope (start with "Entire account" for first upload, then switch to project-specific)
6. **Save the token immediately** - you won't be able to see it again

### 3. Required Tools

Install the necessary Python packages:

```powershell
pip install --upgrade build twine
```

**What these tools do:**

- `build`: Creates distribution packages (wheel and source distribution)
- `twine`: Securely uploads packages to PyPI

## Preparation

### 1. Verify Package Metadata

Ensure your `pyproject.toml` contains accurate metadata:

```toml
[project]
name = "webhook-mcp-server"
version = "2.0.0"
description = "MCP server for webhook management"
# ... other metadata
```

**Key fields to verify:**

- `version`: Current version number (2.0.0)
- `description`: Clear, concise package description
- `authors`: Correct author information
- `license`: Appropriate license
- `readme`: Path to README.md
- `requires-python`: Python version requirements
- `dependencies`: All required packages listed

### 2. Clean Previous Builds

Remove old build artifacts to ensure a clean build:

```powershell
# Remove dist directory if it exists
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# Remove build directory if it exists
if (Test-Path build) { Remove-Item -Recurse -Force build }

# Remove .egg-info directory if it exists
if (Test-Path *.egg-info) { Remove-Item -Recurse -Force *.egg-info }
```

**Why this matters:** Old build artifacts can interfere with new builds or cause outdated files to be published.

### 3. Update Version Number

If publishing a new version, update the version in `pyproject.toml`:

```toml
[project]
version = "2.0.0"  # Update this line
```

**Version numbering follows semantic versioning:**

- `MAJOR.MINOR.PATCH` (e.g., 2.0.0)
- MAJOR: Breaking changes
- MINOR: New features, backward compatible
- PATCH: Bug fixes, backward compatible

### 4. Update Changelog

Document changes in `CHANGELOG.md`:

```markdown
## [2.0.0] - 2026-01-26

### Added

- New feature descriptions

### Changed

- Modified functionality descriptions

### Fixed

- Bug fix descriptions
```

## Building the Package

### 1. Navigate to Project Directory

```powershell
cd c:\Users\zeb\Documents\workspace_for_ai\visualext\webhook-mcp-server
```

### 2. Build Distribution Files

Run the build command:

```powershell
python -m build
```

**Expected output:**

```
* Creating virtualenv isolated environment...
* Installing packages in isolated environment... (setuptools>=61.0)
* Getting build dependencies for sdist...
* Building sdist...
* Building wheel from sdist
* Successfully built webhook-mcp-server-2.0.0.tar.gz and webhook_mcp_server-2.0.0-py3-none-any.whl
```

**What gets created:**

- `dist/webhook-mcp-server-2.0.0.tar.gz`: Source distribution (sdist)
- `dist/webhook_mcp_server-2.0.0-py3-none-any.whl`: Wheel distribution (binary)

### 3. Verify Build Contents

Check that the distribution files were created:

```powershell
Get-ChildItem dist
```

**Expected output:**

```
Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a---          1/26/2026  10:30 AM          45678 webhook-mcp-server-2.0.0.tar.gz
-a---          1/26/2026  10:30 AM          34567 webhook_mcp_server-2.0.0-py3-none-any.whl
```

## Publishing to PyPI

### Option 1: Test PyPI (Recommended First)

Test your package on Test PyPI before publishing to production:

#### 1. Configure Credentials

Create or edit `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YourProductionTokenHere

[testpypi]
username = __token__
password = pypi-YourTestTokenHere
repository = https://test.pypi.org/legacy/
```

**Security note:** Keep this file secure. Never commit it to version control.

#### 2. Upload to Test PyPI

```powershell
twine upload --repository testpypi dist/*
```

**Expected output:**

```
Uploading distributions to https://test.pypi.org/legacy/
Uploading webhook-mcp-server-2.0.0.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45.7/45.7 kB • 00:01 • ?
Uploading webhook_mcp_server-2.0.0-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 34.6/34.6 kB • 00:01 • ?

View at:
https://test.pypi.org/project/webhook-mcp-server/2.0.0/
```

#### 3. Test Installation from Test PyPI

```powershell
# Create a test virtual environment
python -m venv test-env
.\test-env\Scripts\Activate.ps1

# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ webhook-mcp-server

# Test the package
python -c "import webhook_mcp_server; print(webhook_mcp_server.__version__)"

# Deactivate and clean up
deactivate
Remove-Item -Recurse -Force test-env
```

### Option 2: Production PyPI

Once you've verified everything works on Test PyPI:

#### 1. Upload to PyPI

```powershell
twine upload dist/*
```

**Expected output:**

```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading webhook-mcp-server-2.0.0.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45.7/45.7 kB • 00:02 • ?
Uploading webhook_mcp_server-2.0.0-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 34.6/34.6 kB • 00:02 • ?

View at:
https://pypi.org/project/webhook-mcp-server/2.0.0/
```

#### 2. Alternative: Upload with Inline Token

If you haven't configured `.pypirc`:

```powershell
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = "pypi-YourTokenHere"
twine upload dist/*
```

**Note:** This method keeps your token out of configuration files but requires setting it each session.

## Verification

### 1. Check PyPI Page

Visit your package page:

- **Production**: `https://pypi.org/project/webhook-mcp-server/`
- **Test**: `https://test.pypi.org/project/webhook-mcp-server/`

**Verify:**

- ✅ Version number is correct (2.0.0)
- ✅ Description displays properly
- ✅ README renders correctly
- ✅ Dependencies are listed
- ✅ Download files are available

### 2. Test Installation

Install from PyPI in a fresh environment:

```powershell
# Create test environment
python -m venv verify-env
.\verify-env\Scripts\Activate.ps1

# Install package
pip install webhook-mcp-server

# Verify version
python -c "import webhook_mcp_server; print(webhook_mcp_server.__version__)"

# Expected output: 2.0.0

# Clean up
deactivate
Remove-Item -Recurse -Force verify-env
```

### 3. Verify Package Contents

Check that all necessary files are included:

```powershell
pip show -f webhook-mcp-server
```

**Expected to see:**

- Python modules (`.py` files)
- `py.typed` marker file
- License file
- Metadata files

## Troubleshooting

### Common Issues and Solutions

#### 1. "File already exists"

**Error:**

```
HTTPError: 400 Bad Request from https://upload.pypi.org/legacy/
File already exists.
```

**Solution:** You cannot re-upload the same version. Increment the version number in `pyproject.toml` and rebuild.

```powershell
# Edit pyproject.toml: version = "2.0.1"
Remove-Item -Recurse -Force dist
python -m build
twine upload dist/*
```

#### 2. "Invalid username/password"

**Error:**

```
HTTPError: 403 Forbidden from https://upload.pypi.org/legacy/
Invalid or non-existent authentication information.
```

**Solution:** Verify your API token:

- Ensure username is `__token__` (with double underscores)
- Check that token starts with `pypi-`
- Verify token hasn't been revoked
- Try generating a new token

#### 3. Missing Dependencies

**Error during build:**

```
ModuleNotFoundError: No module named 'build'
```

**Solution:**

```powershell
pip install --upgrade build twine setuptools wheel
```

#### 4. "Permission denied" on Windows

**Error:**

```
PermissionError: [WinError 5] Access is denied
```

**Solution:**

- Close any processes using the files (IDEs, terminals)
- Run PowerShell as Administrator
- Check antivirus isn't blocking the operation

#### 5. README Not Rendering

**Issue:** README appears as plain text on PyPI.

**Solution:** Verify `pyproject.toml` specifies correct content type:

```toml
[project]
readme = { file = "README.md", content-type = "text/markdown" }
```

#### 6. Package Structure Issues

**Error:**

```
warning: no files found matching '*.py'
```

**Solution:** Check package structure and ensure `pyproject.toml` has correct package discovery:

```toml
[tool.setuptools]
packages = ["webhook_mcp_server", "webhook_mcp_server.handlers", ...]
```

#### 7. Network/Firewall Issues

**Error:**

```
Could not fetch URL: connection error
```

**Solution:**

- Check internet connection
- Verify firewall/proxy settings
- Try adding `--verbose` to see detailed error:
  ```powershell
  twine upload --verbose dist/*
  ```

## Version Management

### Semantic Versioning Guidelines

Follow semantic versioning (semver) principles:

**Format:** `MAJOR.MINOR.PATCH`

- **MAJOR** (2.x.x): Incompatible API changes
  - Removing features
  - Changing function signatures
  - Breaking backward compatibility

- **MINOR** (x.0.x): New features, backward compatible
  - Adding new endpoints
  - New optional parameters
  - Enhanced functionality

- **PATCH** (x.x.0): Bug fixes, backward compatible
  - Fixing bugs
  - Performance improvements
  - Documentation updates

### Version Update Checklist

Before releasing a new version:

- [ ] Update version in `pyproject.toml`
- [ ] Update `CHANGELOG.md` with changes
- [ ] Update `README.md` if needed
- [ ] Run tests: `pytest`
- [ ] Build package: `python -m build`
- [ ] Test on Test PyPI
- [ ] Verify installation
- [ ] Upload to production PyPI
- [ ] Create git tag: `git tag v2.0.0`
- [ ] Push tag: `git push origin v2.0.0`

### Pre-release Versions

For alpha, beta, or release candidates:

```toml
version = "2.1.0a1"  # Alpha release 1
version = "2.1.0b2"  # Beta release 2
version = "2.1.0rc3" # Release candidate 3
```

## Best Practices

### 1. Always Test First

- Use Test PyPI before production
- Test installation in clean environment
- Verify all functionality works

### 2. Keep Credentials Secure

- Never commit `.pypirc` to git
- Use API tokens instead of passwords
- Use project-scoped tokens when possible
- Rotate tokens periodically

### 3. Maintain Clean Builds

- Remove old build artifacts before building
- Verify package contents before uploading
- Check file sizes are reasonable

### 4. Document Everything

- Maintain detailed CHANGELOG
- Update README with new features
- Document breaking changes clearly

### 5. Version Control

- Tag releases in git
- Keep version numbers consistent
- Follow semantic versioning

### 6. Automation (Advanced)

Consider using GitHub Actions for automated publishing:

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Build package
        run: |
          pip install build
          python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

## Resources

- **PyPI Official Documentation**: [https://packaging.python.org/](https://packaging.python.org/)
- **Twine Documentation**: [https://twine.readthedocs.io/](https://twine.readthedocs.io/)
- **Build Documentation**: [https://build.pypa.io/](https://build.pypa.io/)
- **Semantic Versioning**: [https://semver.org/](https://semver.org/)
- **Python Packaging Guide**: [https://packaging.python.org/guides/](https://packaging.python.org/guides/)

## Support

If you encounter issues not covered in this guide:

1. Check [PyPI Status](https://status.python.org/) for service outages
2. Review [PyPI Help](https://pypi.org/help/)
3. Search [Python Packaging Discourse](https://discuss.python.org/c/packaging/)
4. Consult package maintainers

---

## Step 2: Publish to MCP Registry

The **MCP (Model Context Protocol) Registry** is the official directory where AI applications and Claude Desktop discover available MCP servers. Publishing your server to the registry makes it easily discoverable and installable by users through standardized tools.

### Why Publish to MCP Registry?

- **Discoverability**: Users can find your server through official MCP tools
- **Easy Installation**: Simplified installation through `mcp-publisher` CLI
- **Version Management**: Track and manage server versions
- **Community Trust**: Official registry listing builds credibility
- **Documentation**: Centralized location for server documentation and usage

### Prerequisites

Before publishing to the MCP Registry:

1. **GitHub Account**: You need a GitHub account (username: zebbern)
2. **Published PyPI Package**: Your package must be available on PyPI (complete Step 1 first)
3. **Server Metadata**: Ensure your `pyproject.toml` and README.md are complete
4. **Authentication Token**: GitHub personal access token (created during setup)

### Installing mcp-publisher CLI

The `mcp-publisher` tool handles MCP Registry interactions.

#### Windows Installation

```powershell
# Install using pip
pip install mcp-publisher

# Verify installation
mcp-publisher --version
```

**Expected output:**

```
mcp-publisher version 1.x.x
```

**Troubleshooting installation:**

```powershell
# If command not found, ensure Python Scripts directory is in PATH
$env:Path += ";$env:USERPROFILE\AppData\Local\Programs\Python\Python311\Scripts"

# Or use python -m to run directly
python -m mcp_publisher --version
```

### Authentication with GitHub

MCP Registry uses GitHub for authentication and server identification.

#### 1. Create GitHub Personal Access Token

1. Go to [GitHub Settings → Developer Settings → Personal Access Tokens](https://github.com/settings/tokens)
2. Click "Generate new token" → "Generate new token (classic)"
3. Give it a descriptive name: "mcp-registry-publisher"
4. Select scopes:
   - `repo` (Full control of private repositories)
   - `read:org` (Read org and team membership)
5. Click "Generate token"
6. **Copy the token immediately** - you won't see it again

#### 2. Authenticate mcp-publisher

```powershell
# Authenticate with your GitHub token
mcp-publisher auth login

# When prompted, paste your GitHub token
# Token: ghp_yourTokenHere
```

**Expected output:**

```
✓ Successfully authenticated as zebbern
✓ Token stored securely
```

**Verify authentication:**

```powershell
mcp-publisher auth status
```

**Expected output:**

```
✓ Authenticated as zebbern
✓ Token valid until: 2027-01-26
```

### Publishing the Server to Registry

#### 1. Navigate to Project Directory

```powershell
cd c:\Users\zeb\Documents\workspace_for_ai\visualext\webhook-mcp-server
```

#### 2. Publish to MCP Registry

```powershell
# Publish the server
mcp-publisher publish

# Or specify server name explicitly
mcp-publisher publish --name "io.github.zebbern/webhook-mcp-server"
```

**What happens during publishing:**

1. Validates `pyproject.toml` metadata
2. Checks PyPI for package availability
3. Extracts server configuration from `server.py`
4. Generates MCP Registry manifest
5. Submits to registry with GitHub authentication
6. Creates registry entry under your GitHub username

**Expected output:**

```
✓ Validating package metadata...
✓ Checking PyPI for webhook-mcp-server...
✓ Package found: webhook-mcp-server v2.0.0
✓ Extracting MCP server configuration...
✓ Generating registry manifest...
✓ Publishing to MCP Registry...
✓ Successfully published: io.github.zebbern/webhook-mcp-server
✓ Registry URL: https://mcp.run/servers/io.github.zebbern/webhook-mcp-server
```

#### 3. Provide Additional Metadata (Optional)

Enhance your registry entry with additional information:

```powershell
# Add tags for better discoverability
mcp-publisher publish --tags "webhook,http,automation,testing"

# Add category
mcp-publisher publish --category "Development Tools"

# Add homepage URL
mcp-publisher publish --homepage "https://github.com/zebbern/webhook-mcp-server"
```

### Verification Steps

After publishing, verify your server is correctly listed:

#### 1. Check Registry Listing

```powershell
# View your published server
mcp-publisher show io.github.zebbern/webhook-mcp-server
```

**Expected output:**

```
Server: io.github.zebbern/webhook-mcp-server
Version: 2.0.0
Author: zebbern
Description: MCP server for webhook management
PyPI: https://pypi.org/project/webhook-mcp-server/
Tags: webhook, http, automation, testing
Published: 2026-01-26
```

#### 2. Test Installation via Registry

Test that users can install your server:

```powershell
# Install from MCP Registry
mcp-publisher install io.github.zebbern/webhook-mcp-server

# Or using Claude Desktop's built-in installer
# (This would be done by end-users)
```

#### 3. Verify in Claude Desktop

1. Open Claude Desktop
2. Go to Settings → MCP Servers
3. Click "Install from Registry"
4. Search for "webhook-mcp-server"
5. Verify your server appears with correct metadata

### Updating Existing Registry Entries

When you publish a new version:

#### 1. Update PyPI First

Always update PyPI before updating the registry:

```powershell
# Build new version
python -m build

# Upload to PyPI
twine upload dist/*
```

#### 2. Update Registry Entry

```powershell
# Registry automatically detects new PyPI version
mcp-publisher publish --update

# Or force update with specific version
mcp-publisher publish --version 2.1.0 --update
```

**Expected output:**

```
✓ Detected new version: 2.1.0
✓ Updating registry entry...
✓ Successfully updated: io.github.zebbern/webhook-mcp-server
✓ New version available: 2.1.0
```

#### 3. Update Server Metadata

Update description, tags, or other metadata:

```powershell
# Update description
mcp-publisher update --description "Enhanced MCP server for webhook management and HTTP automation"

# Update tags
mcp-publisher update --tags "webhook,http,automation,testing,mcp"

# Update multiple fields
mcp-publisher update \
  --description "New description" \
  --tags "new,tags" \
  --homepage "https://new-url.com"
```

### Best Practices

#### Version Management

- **Semantic Versioning**: Follow semver (MAJOR.MINOR.PATCH)
- **PyPI First**: Always publish to PyPI before updating registry
- **Changelog**: Maintain detailed changelog for each version
- **Testing**: Test new versions on Test PyPI before production

#### Metadata Quality

- **Clear Description**: Write concise, informative descriptions
- **Relevant Tags**: Use tags that users would search for
- **Accurate Category**: Choose the most appropriate category
- **Complete README**: Include installation, usage, and examples
- **Server Configuration**: Provide example configuration in README

#### Security

- **Token Security**: Never commit GitHub tokens to version control
- **Scope Limitation**: Use minimal required token scopes
- **Token Rotation**: Rotate tokens periodically
- **Dependency Security**: Keep dependencies updated

### Troubleshooting

#### Authentication Issues

**Problem:** `Error: Not authenticated`

```powershell
# Re-authenticate
mcp-publisher auth logout
mcp-publisher auth login
```

**Problem:** `Error: Invalid token`

```powershell
# Generate new GitHub token and re-authenticate
mcp-publisher auth login --force
```

#### Publishing Errors

**Problem:** `Error: Package not found on PyPI`

```powershell
# Ensure package is published to PyPI first
twine upload dist/*

# Wait a few minutes for PyPI to index
# Then retry publishing to registry
```

**Problem:** `Error: Server already exists`

```powershell
# Use --update flag to update existing entry
mcp-publisher publish --update
```

**Problem:** `Error: Invalid server configuration`

```powershell
# Validate your server.py exports correct server object
# Ensure server.py contains:
# app = Server("webhook-mcp-server")
```

#### Network Issues

**Problem:** Timeout or connection errors

```powershell
# Check network connectivity
Test-NetConnection -ComputerName mcp.run -Port 443

# Try with increased timeout
mcp-publisher publish --timeout 60

# Use verbose mode for debugging
mcp-publisher publish --verbose
```

### Registry Configuration Files

#### server.json (Optional)

Create `server.json` for custom registry configuration:

```json
{
  "name": "io.github.zebbern/webhook-mcp-server",
  "displayName": "Webhook MCP Server",
  "description": "Professional webhook management for MCP",
  "version": "2.0.0",
  "author": "zebbern",
  "license": "MIT",
  "homepage": "https://github.com/zebbern/webhook-mcp-server",
  "repository": "https://github.com/zebbern/webhook-mcp-server",
  "keywords": ["webhook", "http", "automation", "testing"],
  "category": "Development Tools",
  "pypi": {
    "package": "webhook-mcp-server",
    "version": "2.0.0"
  },
  "mcp": {
    "server": "server:app",
    "python_version": ">=3.11"
  }
}
```

#### .mcp-registry-ignore

Create `.mcp-registry-ignore` to exclude files:

```
__pycache__/
*.pyc
.env
.venv/
tests/
.git/
```

### Monitoring and Analytics

#### View Server Statistics

```powershell
# View download statistics
mcp-publisher stats io.github.zebbern/webhook-mcp-server

# View version distribution
mcp-publisher stats --versions
```

**Expected output:**

```
Server: io.github.zebbern/webhook-mcp-server
Total Downloads: 1,234
Downloads (Last 30 days): 456
Active Installations: 89
Version Distribution:
  2.0.0: 65%
  1.5.0: 25%
  1.0.0: 10%
```

#### User Feedback

Monitor user feedback and issues:

```powershell
# View registry reviews (if enabled)
mcp-publisher reviews io.github.zebbern/webhook-mcp-server
```

### Unpublishing from Registry

If you need to remove your server:

```powershell
# Unpublish specific version
mcp-publisher unpublish --version 1.0.0

# Unpublish entire server (requires confirmation)
mcp-publisher unpublish io.github.zebbern/webhook-mcp-server
```

**Warning:** Unpublishing affects existing users. Use deprecation instead:

```powershell
# Mark version as deprecated
mcp-publisher deprecate --version 1.0.0 --message "Please upgrade to 2.0.0"
```

### Additional Resources

- **MCP Registry Documentation**: [https://mcp.run/docs/publishing](https://mcp.run/docs/publishing)
- **mcp-publisher CLI Reference**: [https://github.com/modelcontextprotocol/mcp-publisher](https://github.com/modelcontextprotocol/mcp-publisher)
- **MCP Protocol Specification**: [https://spec.modelcontextprotocol.io/](https://spec.modelcontextprotocol.io/)
- **Community Forum**: [https://github.com/modelcontextprotocol/discussions](https://github.com/modelcontextprotocol/discussions)

---

**Last Updated:** January 26, 2026  
**Package Version:** 2.0.0  
**Guide Version:** 1.0
