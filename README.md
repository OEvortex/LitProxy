<div align="center">
  <a href="https://github.com/OEvortex/Webscout/tree/main/Litproxy">
    <img src="https://img.shields.io/badge/LitProxy-Modern%20Proxy%20Management-green?style=for-the-badge&logo=python&logoColor=white" alt="LitProxy Logo">
  </a>

  <h1>LitProxy</h1>

  <p><strong>Modern, Easy-to-Use Python Proxy Management Library</strong></p>

  <p>
    Intelligent proxy rotation, seamless HTTP client patching, context management, and comprehensive diagnostics for Python applications. Make proxy usage simple and universal across any Python project.
  </p>

  <!-- Badges -->
  <p>
    <a href="https://pypi.org/project/litproxy/"><img src="https://img.shields.io/pypi/v/litproxy.svg?style=flat-square&logo=pypi&label=PyPI" alt="PyPI Version"></a>
    <a href="#"><img src="https://img.shields.io/pypi/pyversions/litproxy?style=flat-square&logo=python" alt="Python Version"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License"></a>
    <a href="#"><img src="https://img.shields.io/badge/Status-Beta-orange.svg?style=flat-square" alt="Status"></a>
  </p>
</div>

<hr/>

## 📋 Table of Contents

- [🌟 Key Features](#-key-features)
- [⚙️ Installation](#️-installation)
- [🚀 Quick Start](#-quick-start)
- [📖 Usage Examples](#-usage-examples)
- [🔧 Advanced Features](#-advanced-features)
- [🌐 Proxy Sources](#-proxy-sources)
- [🛠️ HTTP Client Support](#️-http-client-support)
- [📊 Diagnostics & Monitoring](#-diagnostics--monitoring)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

<hr/>

## 🌟 Key Features

<details open>
<summary><b>🔄 Intelligent Proxy Management</b></summary>
<p>

- **Smart Rotation:** Automatic proxy rotation with random selection (no priority)
- **Health Monitoring:** Built-in proxy testing and health checks with configurable timeouts
- **Caching System:** Efficient proxy caching with background refresh to minimize latency
- **Fallback Support:** Automatic fallback to alternative proxies when primary sources fail

</p>
</details>

<details open>
<summary><b>🔌 Universal HTTP Client Support</b></summary>
<p>

- **Requests Integration:** Seamless integration with Python's `requests` library
- **HTTPX Support:** Full compatibility with modern `httpx` async/sync clients
- **Curl_cffi Support:** Advanced browser impersonation with `curl_cffi` sessions
- **Auto-Patching:** Automatic proxy injection into existing HTTP sessions

</p>
</details>

<details open>
<summary><b>🎯 Developer-Friendly API</b></summary>
<p>

- **Context Managers:** Clean proxy usage with Python context managers
- **Decorators:** Simple function decoration for automatic proxy injection
- **Metaclass Magic:** Automatic proxy injection for class-based applications
- **Static Methods:** Direct access to proxy functionality without instantiation

</p>
</details>

<details open>
<summary><b>🛡️ Reliability & Diagnostics</b></summary>
<p>

- **Auto-Retry Logic:** Intelligent retry mechanisms with proxy rotation on failures
- **Comprehensive Testing:** Built-in proxy validation and performance testing
- **Statistics & Monitoring:** Detailed proxy usage statistics and cache metrics
- **Error Handling:** Graceful degradation when proxies are unavailable

</p>
</details>

<hr/>

## ⚙️ Installation

### 📦 Standard Installation

```bash
# Install from PyPI
pip install litproxy

# Install from local directory
pip install .

# Install in development mode
pip install -e .
```

### 🔧 Dependencies

**Required:**
- `requests>=2.25.0`

**Optional (for extended functionality):**
- `httpx` - For modern async/sync HTTP client support
- `curl_cffi` - For advanced browser impersonation capabilities

```bash
# Install with optional dependencies
pip install httpx curl_cffi
```

<hr/>

## 🚀 Quick Start

### Basic Usage

```python
from litproxy import LitProxy
import requests

# Initialize LitProxy
proxy = LitProxy()

# Method 1: Context Manager (Recommended)
with proxy.use_proxy():
    response = requests.get("https://httpbin.org/ip")
    print(response.json())

# Method 2: Direct Proxy Dictionary
proxies = proxy.get_proxy_dict()
response = requests.get("https://httpbin.org/ip", proxies=proxies)

# Method 3: Decorator
@proxy.proxyify
def fetch_data(url):
    return requests.get(url)

result = fetch_data("https://httpbin.org/ip")
```

### Auto-Retry with Proxy Rotation

```python
from litproxy import LitProxy

# Create session with automatic retry and proxy rotation
session = LitProxy.create_auto_retry_session(max_proxy_attempts=3)

# This will automatically retry with different proxies on failure
response = session.get("https://httpbin.org/ip")
```

<hr/>

## 📖 Usage Examples

### Context Manager Usage

```python
from litproxy import LitProxy
import requests

proxy = LitProxy()

# Global proxy patching for all requests
with proxy.use_proxy():
    # All requests in this block will use proxies
    response1 = requests.get("https://httpbin.org/ip")
    response2 = requests.get("https://httpbin.org/user-agent")
    
    print("IP 1:", response1.json()['origin'])
    print("IP 2:", response2.json()['origin'])
```

### Decorator Pattern

```python
from litproxy import LitProxy

@LitProxy.proxyify
def scrape_website(url):
    import requests
    return requests.get(url).text

@LitProxy.auto_retry_with_fallback(max_proxy_attempts=5)
def robust_request(url):
    import requests
    return requests.get(url)

# These functions will automatically use proxies
content = scrape_website("https://httpbin.org/html")
response = robust_request("https://httpbin.org/ip")
```

### Session Management

```python
from litproxy import LitProxy

# Get pre-configured sessions for different HTTP clients
requests_session = LitProxy.get_proxied_session()
httpx_client = LitProxy.get_proxied_httpx_client()
curl_session = LitProxy.get_proxied_curl_session(impersonate="chrome120")

# Use sessions normally - proxies are already configured
response = requests_session.get("https://httpbin.org/ip")

# Advanced session management with auto-retry
auto_retry_session = LitProxy.create_auto_retry_session(max_proxy_attempts=3)
response = auto_retry_session.get("https://httpbin.org/ip")  # Automatically retries with different proxies

# Patch existing sessions with auto-retry functionality
import requests
my_session = requests.Session()
LitProxy.patch(my_session)  # Adds proxy support
```

### Class-Based Applications with Metaclass

```python
from litproxy import LitMeta
import requests

class WebScraper(metaclass=LitMeta):
    def __init__(self):
        self.session = requests.Session()
    
    def scrape(self, url):
        # Session automatically has proxies injected
        return self.session.get(url)

# Proxies are automatically configured
scraper = WebScraper()
response = scraper.scrape("https://httpbin.org/ip")
```

<hr/>

## 🔧 Advanced Features

### Manual Proxy Selection

```python
from litproxy import LitProxy

# Get a random working proxy from all available sources
random_proxy = LitProxy.get_working_proxy()
any_proxy = LitProxy.get_auto_proxy()          # Random selection

# Test specific proxy
proxy_url = "http://proxy.example.com:8080"
is_working = LitProxy.test_proxy(proxy_url, timeout=10)

# Get all available proxies
all_proxies = LitProxy.list_proxies()

# Force refresh proxy cache
proxy_count = LitProxy.refresh_proxy_cache()
print(f"Loaded {proxy_count} proxies")
```

### Proxy Testing and Diagnostics

```python
from litproxy import LitProxy

# Test all available proxies
test_results = LitProxy.test_all_proxies(timeout=5)
for proxy, status in test_results.items():
    print(f"{proxy}: {'✓' if status else '✗'}")

# Get proxy statistics
stats = LitProxy.get_proxy_stats()
print(f"Available proxies: {stats['proxy_count']}")
print(f"Cache age: {stats['cache_age_seconds']} seconds")
```

### Custom Configuration

```python
from litproxy import LitProxy

# Configure cache duration (default: 300 seconds)
LitProxy.set_proxy_cache_duration(600)  # 10 minutes

# Manual request with retry logic
response = LitProxy.make_request_with_auto_retry(
    method="GET",
    url="https://httpbin.org/ip",
    max_proxy_attempts=3,
    timeout=10
)

# Enable/disable auto-retry for existing provider instances
LitProxy.enable_auto_retry_for_provider(my_provider, max_proxy_attempts=5)
LitProxy.disable_auto_retry_for_provider(my_provider)
```

### Enhanced Auto-Retry Features

```python
from litproxy import LitProxy

# Create session with enhanced auto-retry
session = LitProxy.create_auto_retry_session(max_proxy_attempts=3)

# Make requests with automatic proxy rotation on failure
response = session.get("https://httpbin.org/ip")

# Direct auto-retry request without session
response = LitProxy.make_request_with_auto_retry(
    method="POST",
    url="https://httpbin.org/post",
    json={"data": "test"},
    max_proxy_attempts=5,
    timeout=15
)

# Enhanced decorator with intelligent proxy fallback
@LitProxy.auto_retry_with_fallback(max_proxy_attempts=3)
def robust_api_call(url, data):
    import requests
    return requests.post(url, json=data)

result = robust_api_call("https://api.example.com/data", {"key": "value"})
```

<hr/>

## 🌐 Proxy Sources

LitProxy supports multiple proxy sources with no prioritization:

### 1. **Webshare Proxies**
- Premium rotating proxies from Webshare.io
- High reliability and performance
- Used equally with other sources

### 2. **Remote Proxy Lists**
- Dynamic proxy lists fetched from remote sources
- Automatically updated and cached
- Background refresh to maintain availability

### 3. **NordVPN Proxies**
- Static NordVPN proxy endpoints
- Used equally with other sources
- Reliable but may have usage limitations



<hr/>

## 🛠️ HTTP Client Support

### Requests Library

```python
import requests
from litproxy import LitProxy

# Method 1: Session patching with auto-retry
session = requests.Session()
LitProxy.patch(session)  # Adds proxy support
response = session.get("https://httpbin.org/ip")

# Method 2: Enhanced session with auto-retry
session = LitProxy.create_auto_retry_session(max_proxy_attempts=3)
response = session.get("https://httpbin.org/ip")  # Automatically retries with different proxies

# Method 3: Direct proxy injection
proxies = LitProxy.get_proxy_dict()
response = requests.get("https://httpbin.org/ip", proxies=proxies)
```

### HTTPX Client

```python
import httpx
from litproxy import LitProxy

# Sync client with proxy support
client = LitProxy.get_proxied_httpx_client()
response = client.get("https://httpbin.org/ip")

# Patch existing httpx client
client = httpx.Client()
LitProxy.patch(client)  # Adds proxy support
response = client.get("https://httpbin.org/ip")

# Async client
async with LitProxy.get_proxied_httpx_client() as client:
    response = await client.get("https://httpbin.org/ip")
```

### Curl_cffi Sessions

```python
from litproxy import LitProxy

# Sync session with browser impersonation
session = LitProxy.get_proxied_curl_session(impersonate="chrome120")
response = session.get("https://httpbin.org/ip")

# Async session
async_session = LitProxy.get_proxied_curl_async_session(impersonate="safari15_5")
```

<hr/>

## 📊 Diagnostics & Monitoring

### Proxy Statistics

```python
from litproxy import LitProxy

stats = LitProxy.get_proxy_stats()
print(f"""
Proxy Statistics:
- Available Proxies: {stats['proxy_count']}
- Last Updated: {stats['last_updated']}
- Cache Duration: {stats['cache_duration']} seconds
- Cache Age: {stats['cache_age_seconds']} seconds
- Source URL: {stats['source_url']}
""")
```

### Health Monitoring

```python
from litproxy import LitProxy

# Test current proxy
current = LitProxy.current_proxy()
if current:
    is_healthy = LitProxy.test_proxy(current)
    print(f"Current proxy {current} is {'healthy' if is_healthy else 'unhealthy'}")

# Comprehensive health check
health_report = LitProxy.test_all_proxies()
healthy_count = sum(1 for status in health_report.values() if status)
total_count = len(health_report)
print(f"Healthy proxies: {healthy_count}/{total_count}")
```

<hr/>

## 🤝 Contributing

We welcome contributions to LitProxy! Here's how you can help:

### Development Setup

```bash
# Clone the repository
git clone https://github.com/OEvortex/Webscout.git
cd Webscout/Litproxy

# Install in development mode
pip install -e .

# Install development dependencies
pip install pytest httpx curl_cffi
```

### Running Tests

```bash
# Run basic tests
python -m pytest

# Test with different HTTP clients
python -c "from litproxy import LitProxy; print('✓ Basic import works')"
```

### Areas for Contribution

- 🐛 **Bug Reports:** Found an issue? Please report it!
- 🚀 **Feature Requests:** Have ideas for improvements?
- 📖 **Documentation:** Help improve our docs and examples
- 🧪 **Testing:** Add test cases for better coverage
- 🔌 **Integrations:** Support for additional HTTP clients

<hr/>

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">
  <p><strong>Made with ❤️ by the Webscout Team</strong></p>
  <p>
    <a href="https://github.com/OEvortex/Webscout">🏠 Main Project</a> •
    <a href="https://github.com/OEvortex/Webscout/issues">🐛 Report Bug</a> •
    <a href="https://github.com/OEvortex/Webscout/issues">💡 Request Feature</a>
  </p>
</div>
