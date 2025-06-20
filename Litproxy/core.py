"""
This module provides automatic proxy injection for HTTP sessions using a remote proxy list.
"""

import random
import time
from abc import ABCMeta
from typing import Dict, List, Optional, Any, Callable, Union
import requests
import functools
from contextlib import contextmanager
import types
import re
from urllib.parse import quote, urlparse, urlunparse

# Optional imports for different HTTP clients
try:
    import httpx
except ImportError:
    httpx = None

try:
    from curl_cffi.requests import Session as CurlSession
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
except ImportError:
    CurlSession = None
    CurlAsyncSession = None

# Global proxy cache
_proxy_cache = {
    'proxies': [],
    'last_updated': 0,
    'cache_duration': 300  # 5 minutes
}

PROXY_SOURCE_URL = "http://207.180.209.185:5000/ips.txt"


def fetch_proxies() -> List[str]:
    """
    Fetch proxy list from the remote source.

    Returns:
        List[str]: List of proxy URLs in format 'http://user:pass@host:port'
    """
    try:
        response = requests.get(PROXY_SOURCE_URL, timeout=10)
        response.raise_for_status()

        proxies = []
        for line in response.text.strip().split('\n'):
            line = line.strip()
            if line and line.startswith('http://'):
                proxies.append(line)

        return proxies

    except Exception:
        return []


def get_cached_proxies() -> List[str]:
    """
    Get proxies from cache or fetch new ones if cache is expired.

    Returns:
        List[str]: List of proxy URLs
    """
    current_time = time.time()

    # Check if cache is expired or empty
    if (current_time - _proxy_cache['last_updated'] > _proxy_cache['cache_duration'] or
        not _proxy_cache['proxies']):

        new_proxies = fetch_proxies()
        if new_proxies:
            _proxy_cache['proxies'] = new_proxies
            _proxy_cache['last_updated'] = current_time
        else:
            pass

    # Only use remote proxies, no static proxies
    proxies = _proxy_cache['proxies']
    proxies = list(dict.fromkeys(proxies))  # Remove duplicates, preserve order
    return proxies


def get_auto_proxy() -> Optional[str]:
    """
    Get a random proxy from the remote list.

    Returns:
        Optional[str]: A proxy URL or None if no proxies available
    """
    proxies = get_cached_proxies()
    if proxies:
        return random.choice(proxies)
    return None


def get_proxy_dict(proxy_url: Optional[str] = None) -> Dict[str, str]:
    """
    Convert a proxy URL to a dictionary format suitable for requests/httpx.

    Args:
        proxy_url: Proxy URL, if None will get one automatically

    Returns:
        Dict[str, str]: Proxy dictionary with 'http' and 'https' keys
    """
    if proxy_url is None:
        proxy_url = get_auto_proxy()

    if proxy_url is None:
        return {}

    # URL-encode username and password if present
    parsed = urlparse(proxy_url)
    if parsed.username and parsed.password:
        safe_user = quote(parsed.username, safe='')
        safe_pass = quote(parsed.password, safe='')
        netloc = f"{safe_user}:{safe_pass}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        encoded_proxy_url = urlunparse((parsed.scheme, netloc, '', '', '', ''))
    else:
        encoded_proxy_url = proxy_url

    return {
        'http': encoded_proxy_url,
        'https': encoded_proxy_url
    }


def test_proxy(proxy_url: str, timeout: int = 10) -> bool:
    """
    Test if a proxy is working by making a request to a test URL.

    Args:
        proxy_url: The proxy URL to test
        timeout: Request timeout in seconds

    Returns:
        bool: True if proxy is working, False otherwise
    """
    try:
        test_url = "https://httpbin.org/ip"
        # URL-encode username and password if present
        parsed = urlparse(proxy_url)
        if parsed.username and parsed.password:
            safe_user = quote(parsed.username, safe='')
            safe_pass = quote(parsed.password, safe='')
            netloc = f"{safe_user}:{safe_pass}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            encoded_proxy_url = urlunparse((parsed.scheme, netloc, '', '', '', ''))
        else:
            encoded_proxy_url = proxy_url
        proxies = {'http': encoded_proxy_url, 'https': encoded_proxy_url}
        response = requests.get(test_url, proxies=proxies, timeout=timeout)
        return response.status_code == 200
    except Exception as e:
        print(f"Proxy test failed for {proxy_url}: {str(e)}")
        return False


class LitMeta(ABCMeta):
    """
    Metaclass to ensure all OpenAICompatibleProvider subclasses automatically get proxy support.
    This will inject proxies into any requests.Session, httpx.Client, or curl_cffi session attributes found on the instance.

    To disable automatic proxy injection, set disable_auto_proxy=True in the constructor or
    set the class attribute DISABLE_AUTO_PROXY = True.
    """

    def __call__(cls, *args, **kwargs):
        instance = super().__call__(*args, **kwargs)

        # Check if auto proxy is disabled
        disable_auto_proxy = kwargs.get('disable_auto_proxy', False) or getattr(cls, 'DISABLE_AUTO_PROXY', False)

        # Get proxies from various sources
        proxies = getattr(instance, 'proxies', None) or kwargs.get('proxies', None)

        if proxies is None and not disable_auto_proxy:
            try:
                proxy_url = get_auto_proxy()
                if proxy_url:
                    proxies = get_proxy_dict(proxy_url)
                else:
                    proxies = {}
            except Exception:
                proxies = {}
        elif proxies is None:
            proxies = {}

        instance.proxies = proxies
        
        # Set default max proxy attempts for auto-retry functionality
        if not hasattr(instance, '_max_proxy_attempts'):
            instance._max_proxy_attempts = kwargs.get('max_proxy_attempts', 2)

        # Always patch existing sessions (for both proxy and auto-retry functionality)
        _patch_instance_sessions(instance, proxies)

        # Provide helper methods for creating proxied sessions
        _add_proxy_helpers(instance, proxies)

        return instance


def _patch_instance_sessions(instance: Any, proxies: Dict[str, str]) -> None:
    """
    Patch existing session objects on the instance with proxy configuration and auto-retry functionality.

    Args:
        instance: The class instance to patch
        proxies: Proxy dictionary to apply
    """
    for attr_name in dir(instance):
        if attr_name.startswith('_'):
            continue

        try:
            attr_obj = getattr(instance, attr_name)

            # Patch requests.Session objects
            if isinstance(attr_obj, requests.Session):
                if proxies:
                    attr_obj.proxies.update(proxies)
                _add_auto_retry_to_session(attr_obj, instance)

            # Patch httpx.Client objects
            elif httpx and isinstance(attr_obj, httpx.Client):
                try:
                    # httpx uses different proxy format
                    if proxies:
                        attr_obj._proxies = proxies
                    _add_auto_retry_to_httpx_client(attr_obj, instance)
                except Exception:
                    pass

            # Patch curl_cffi Session objects
            elif CurlSession and isinstance(attr_obj, CurlSession):
                try:
                    if proxies:
                        attr_obj.proxies.update(proxies)
                    _add_auto_retry_to_curl_session(attr_obj, instance)
                except Exception:
                    pass

            # Patch curl_cffi AsyncSession objects
            elif CurlAsyncSession and isinstance(attr_obj, CurlAsyncSession):
                try:
                    if proxies:
                        attr_obj.proxies.update(proxies)
                    _add_auto_retry_to_curl_async_session(attr_obj, instance)
                except Exception:
                    pass

        except Exception:
            continue


def _add_auto_retry_to_session(session: requests.Session, instance: Any) -> None:
    """
    Add auto-retry functionality to a requests.Session object.
    
    Args:
        session: The requests.Session to patch
        instance: The provider instance for context
    """
    if hasattr(session, '_auto_retry_patched'):
        return  # Already patched
    
    original_request = session.request
    
    def request_with_auto_retry(method, url, **kwargs):
        max_proxy_attempts = getattr(instance, '_max_proxy_attempts', 2)
        original_proxies = session.proxies.copy()
        first_error = None
        
        # First attempt with current proxy configuration
        try:
            return original_request(method, url, **kwargs)
        except Exception as e:
            first_error = e
        
        # If we have proxies configured, try different ones
        if original_proxies:
            proxy_attempts = 0
            
            while proxy_attempts < max_proxy_attempts:
                try:
                    # Get a new proxy
                    new_proxy_url = get_auto_proxy()
                    if new_proxy_url:
                        new_proxies = get_proxy_dict(new_proxy_url)
                        session.proxies.clear()
                        session.proxies.update(new_proxies)
                        
                        # Try the request with new proxy
                        return original_request(method, url, **kwargs)
                    else:
                        break  # No more proxies available
                        
                except Exception:
                    proxy_attempts += 1
                    continue
            
            # All proxy attempts failed, try without proxy
            try:
                session.proxies.clear()
                return original_request(method, url, **kwargs)
            except Exception:
                # Restore original proxy settings and re-raise the first error
                session.proxies.clear()
                session.proxies.update(original_proxies)
                raise first_error
        else:
            # No proxies were configured, just re-raise the original error
            raise first_error
    
    session.request = request_with_auto_retry
    session._auto_retry_patched = True


def _add_auto_retry_to_httpx_client(client, instance: Any) -> None:
    """
    Add auto-retry functionality to an httpx.Client object.
    
    Args:
        client: The httpx.Client to patch
        instance: The provider instance for context
    """
    if not httpx or hasattr(client, '_auto_retry_patched'):
        return  # Not available or already patched
    
    try:
        original_request = client.request
        
        def request_with_auto_retry(method, url, **kwargs):
            max_proxy_attempts = getattr(instance, '_max_proxy_attempts', 2)
            original_proxies = getattr(client, '_proxies', {}).copy()
            first_error = None
            
            # First attempt with current proxy configuration
            try:
                return original_request(method, url, **kwargs)
            except Exception as e:
                first_error = e
            
            # If we have proxies configured, try different ones
            if original_proxies:
                proxy_attempts = 0
                
                while proxy_attempts < max_proxy_attempts:
                    try:
                        # Get a new proxy
                        new_proxy_url = get_auto_proxy()
                        if new_proxy_url:
                            new_proxies = get_proxy_dict(new_proxy_url)
                            client._proxies = new_proxies
                            
                            # Try the request with new proxy
                            return original_request(method, url, **kwargs)
                        else:
                            break  # No more proxies available
                            
                    except Exception:
                        proxy_attempts += 1
                        continue
                
                # All proxy attempts failed, try without proxy
                try:
                    client._proxies = {}
                    return original_request(method, url, **kwargs)
                except Exception:
                    # Restore original proxy settings and re-raise the first error
                    client._proxies = original_proxies
                    raise first_error
            else:
                # No proxies were configured, just re-raise the original error
                raise first_error
        
        client.request = request_with_auto_retry
        client._auto_retry_patched = True
    except Exception:
        pass


def _add_auto_retry_to_curl_session(session, instance: Any) -> None:
    """
    Add auto-retry functionality to a curl_cffi.Session object.
    
    Args:
        session: The curl_cffi.Session to patch
        instance: The provider instance for context
    """
    if not CurlSession or hasattr(session, '_auto_retry_patched'):
        return  # Not available or already patched
    
    try:
        original_request = session.request
        
        def request_with_auto_retry(method, url, **kwargs):
            max_proxy_attempts = getattr(instance, '_max_proxy_attempts', 2)
            original_proxies = session.proxies.copy()
            first_error = None
            
            # First attempt with current proxy configuration
            try:
                return original_request(method, url, **kwargs)
            except Exception as e:
                first_error = e
            
            # If we have proxies configured, try different ones
            if original_proxies:
                proxy_attempts = 0
                
                while proxy_attempts < max_proxy_attempts:
                    try:
                        # Get a new proxy
                        new_proxy_url = get_auto_proxy()
                        if new_proxy_url:
                            new_proxies = get_proxy_dict(new_proxy_url)
                            session.proxies.clear()
                            session.proxies.update(new_proxies)
                            
                            # Try the request with new proxy
                            return original_request(method, url, **kwargs)
                        else:
                            break  # No more proxies available
                            
                    except Exception:
                        proxy_attempts += 1
                        continue
                
                # All proxy attempts failed, try without proxy
                try:
                    session.proxies.clear()
                    return original_request(method, url, **kwargs)
                except Exception:
                    # Restore original proxy settings and re-raise the first error
                    session.proxies.clear()
                    session.proxies.update(original_proxies)
                    raise first_error
            else:
                # No proxies were configured, just re-raise the original error
                raise first_error
        
        session.request = request_with_auto_retry
        session._auto_retry_patched = True
    except Exception:
        pass


def _add_auto_retry_to_curl_async_session(session, instance: Any) -> None:
    """
    Add auto-retry functionality to a curl_cffi.AsyncSession object.
    
    Args:
        session: The curl_cffi.AsyncSession to patch
        instance: The provider instance for context
    """
    if not CurlAsyncSession or hasattr(session, '_auto_retry_patched'):
        return  # Not available or already patched
    
    try:
        original_request = session.request
        
        async def request_with_auto_retry(method, url, **kwargs):
            max_proxy_attempts = getattr(instance, '_max_proxy_attempts', 2)
            original_proxies = session.proxies.copy()
            first_error = None
            
            # First attempt with current proxy configuration
            try:
                return await original_request(method, url, **kwargs)
            except Exception as e:
                first_error = e
            
            # If we have proxies configured, try different ones
            if original_proxies:
                proxy_attempts = 0
                
                while proxy_attempts < max_proxy_attempts:
                    try:
                        # Get a new proxy
                        new_proxy_url = get_auto_proxy()
                        if new_proxy_url:
                            new_proxies = get_proxy_dict(new_proxy_url)
                            session.proxies.clear()
                            session.proxies.update(new_proxies)
                            
                            # Try the request with new proxy
                            return await original_request(method, url, **kwargs)
                        else:
                            break  # No more proxies available
                            
                    except Exception:
                        proxy_attempts += 1
                        continue
                
                # All proxy attempts failed, try without proxy
                try:
                    session.proxies.clear()
                    return await original_request(method, url, **kwargs)
                except Exception:
                    # Restore original proxy settings and re-raise the first error
                    session.proxies.clear()
                    session.proxies.update(original_proxies)
                    raise first_error
            else:
                # No proxies were configured, just re-raise the original error
                raise first_error
        
        session.request = request_with_auto_retry
        session._auto_retry_patched = True
    except Exception:
        pass


def _add_proxy_helpers(instance: Any, proxies: Dict[str, str]) -> None:
    """
    Add helper methods to the instance for creating proxied sessions.

    Args:
        instance: The class instance to add methods to
        proxies: Proxy dictionary to use in helper methods
    """

    def get_proxied_session():
        """Get a requests.Session with proxies configured"""
        session = requests.Session()
        session.proxies.update(proxies)
        return session

    def get_proxied_httpx_client(**kwargs):
        """Get an httpx.Client with proxies configured"""
        if httpx:
            return httpx.Client(proxies=proxies, **kwargs)
        else:
            raise ImportError("httpx is not installed")

    def get_proxied_curl_session(impersonate="chrome120", **kwargs):
        """Get a curl_cffi Session with proxies configured"""
        if CurlSession:
            return CurlSession(proxies=proxies, impersonate=impersonate, **kwargs)
        else:
            raise ImportError("curl_cffi is not installed")

    def get_proxied_curl_async_session(impersonate="chrome120", **kwargs):
        """Get a curl_cffi AsyncSession with proxies configured"""
        if CurlAsyncSession:
            return CurlAsyncSession(proxies=proxies, impersonate=impersonate, **kwargs)
        else:
            raise ImportError("curl_cffi is not installed")

    def get_auto_retry_session(max_proxy_attempts: int = 2):
        """Get a requests.Session with automatic proxy retry and fallback functionality"""
        return create_auto_retry_session(max_proxy_attempts)

    def make_auto_retry_request(method: str, url: str, max_proxy_attempts: int = 2, **kwargs):
        """Make a request with automatic proxy retry and fallback"""
        return make_request_with_auto_retry(
            method=method,
            url=url,
            max_proxy_attempts=max_proxy_attempts,
            **kwargs
        )

    def patch_session_with_auto_retry(session_obj):
        """Patch any session object with auto-retry functionality"""
        if isinstance(session_obj, requests.Session):
            _add_auto_retry_to_session(session_obj, instance)
        elif httpx and isinstance(session_obj, httpx.Client):
            _add_auto_retry_to_httpx_client(session_obj, instance)
        elif CurlSession and isinstance(session_obj, CurlSession):
            _add_auto_retry_to_curl_session(session_obj, instance)
        elif CurlAsyncSession and isinstance(session_obj, CurlAsyncSession):
            _add_auto_retry_to_curl_async_session(session_obj, instance)
        return session_obj

    # Add methods to instance
    instance.get_proxied_session = get_proxied_session
    instance.get_proxied_httpx_client = get_proxied_httpx_client
    instance.get_proxied_curl_session = get_proxied_curl_session
    instance.get_proxied_curl_async_session = get_proxied_curl_async_session
    instance.get_auto_retry_session = get_auto_retry_session
    instance.make_auto_retry_request = make_auto_retry_request
    instance.patch_session_with_auto_retry = patch_session_with_auto_retry


def get_working_proxy(max_attempts: int = 5, timeout: int = 10) -> Optional[str]:
    """
    Get a working proxy by testing multiple proxies from the list.

    Args:
        max_attempts: Maximum number of proxies to test
        timeout: Timeout for each proxy test

    Returns:
        Optional[str]: A working proxy URL or None if none found
    """
    proxies = get_cached_proxies()
    if not proxies:
        return None

    # Shuffle to avoid always testing the same proxies first
    test_proxies = random.sample(proxies, min(max_attempts, len(proxies)))

    for proxy in test_proxies:
        if test_proxy(proxy, timeout):
            return proxy

    return None


def refresh_proxy_cache() -> int:
    """
    Force refresh the proxy cache.

    Returns:
        int: Number of proxies loaded
    """
    global _proxy_cache
    _proxy_cache['last_updated'] = 0  # Force refresh
    proxies = get_cached_proxies()
    return len(proxies)


def get_proxy_stats() -> Dict[str, Any]:
    """
    Get statistics about the proxy cache.

    Returns:
        Dict[str, Any]: Statistics including count, last update time, etc.
    """
    return {
        'proxy_count': len(_proxy_cache['proxies']),
        'last_updated': _proxy_cache['last_updated'],
        'cache_duration': _proxy_cache['cache_duration'],
        'cache_age_seconds': time.time() - _proxy_cache['last_updated'],
        'source_url': PROXY_SOURCE_URL
    }


def set_proxy_cache_duration(duration: int) -> None:
    """
    Set the proxy cache duration.

    Args:
        duration: Cache duration in seconds
    """
    global _proxy_cache
    _proxy_cache['cache_duration'] = duration


def auto_retry_with_fallback(max_proxy_attempts: int = 2, timeout: int = 10):
    """
    Decorator that automatically retries requests with different proxies and falls back to no proxy.
    
    This decorator will:
    1. Try the request with the current proxy
    2. If it fails, try with up to max_proxy_attempts different proxies
    3. If all proxies fail, retry without any proxy
    
    Args:
        max_proxy_attempts: Maximum number of proxy attempts before falling back to no proxy
        timeout: Timeout for each request attempt
    
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Track the original instance and its proxy settings
            instance = args[0] if args else None
            original_proxies = getattr(instance, 'proxies', {}) if instance else {}
            
            # First attempt with current proxy configuration
            try:
                return func(*args, **kwargs)
            except Exception as e:
                first_error = e
                
                # If we have proxies configured, try different ones
                if original_proxies and instance:
                    proxy_attempts = 0
                    
                    while proxy_attempts < max_proxy_attempts:
                        try:
                            # Get a new proxy
                            new_proxy_url = get_auto_proxy()
                            if new_proxy_url:
                                new_proxies = get_proxy_dict(new_proxy_url)
                                instance.proxies = new_proxies
                                
                                # Update any existing sessions with new proxy
                                _patch_instance_sessions(instance, new_proxies)
                                
                                # Try the request with new proxy
                                return func(*args, **kwargs)
                            else:
                                break  # No more proxies available
                                
                        except Exception:
                            proxy_attempts += 1
                            continue
                    
                    # All proxy attempts failed, try without proxy
                    try:
                        instance.proxies = {}
                        _patch_instance_sessions(instance, {})
                        return func(*args, **kwargs)
                    except Exception:
                        # Restore original proxy settings and re-raise the first error
                        instance.proxies = original_proxies
                        _patch_instance_sessions(instance, original_proxies)
                        raise first_error
                else:
                    # No proxies were configured, just re-raise the original error
                    raise first_error
                    
        return wrapper
    return decorator


def make_request_with_auto_retry(
    method: str,
    url: str,
    session: Optional[Union[requests.Session, Any]] = None,
    max_proxy_attempts: int = 2,
    timeout: int = 10,
    **kwargs
) -> requests.Response:
    """
    Make an HTTP request with automatic proxy retry and fallback.
    
    This function will:
    1. Try the request with the current session configuration
    2. If it fails and proxies are configured, try with different proxies
    3. If all proxies fail, retry without any proxy
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        session: Optional session object to use
        max_proxy_attempts: Maximum number of proxy attempts before falling back
        timeout: Request timeout
        **kwargs: Additional arguments to pass to the request
    
    Returns:
        requests.Response: The successful response
        
    Raises:
        Exception: If all attempts fail
    """
    if session is None:
        session = requests.Session()
    
    original_proxies = getattr(session, 'proxies', {}).copy()
    first_error = None
    
    # First attempt with current configuration
    try:
        return session.request(method, url, timeout=timeout, **kwargs)
    except Exception as e:
        first_error = e
    
    # If we have proxies configured, try different ones
    if original_proxies:
        proxy_attempts = 0
        
        while proxy_attempts < max_proxy_attempts:
            try:
                # Get a new proxy
                new_proxy_url = get_auto_proxy()
                if new_proxy_url:
                    new_proxies = get_proxy_dict(new_proxy_url)
                    session.proxies.clear()
                    session.proxies.update(new_proxies)
                    
                    # Try the request with new proxy
                    return session.request(method, url, timeout=timeout, **kwargs)
                else:
                    break  # No more proxies available
                    
            except Exception:
                proxy_attempts += 1
                continue
        
        # All proxy attempts failed, try without proxy
        try:
            session.proxies.clear()
            return session.request(method, url, timeout=timeout, **kwargs)
        except Exception:
            # Restore original proxy settings and re-raise the first error
            session.proxies.clear()
            session.proxies.update(original_proxies)
            raise first_error
    else:
        # No proxies were configured, just re-raise the original error
        raise first_error


def create_auto_retry_session(max_proxy_attempts: int = 2) -> requests.Session:
    """
    Create a requests.Session with automatic proxy retry functionality.
    
    Args:
        max_proxy_attempts: Maximum number of proxy attempts before falling back
        
    Returns:
        requests.Session: Session with auto-retry functionality
    """
    session = requests.Session()
    
    # Get initial proxy configuration
    proxy_url = get_auto_proxy()
    if proxy_url:
        proxies = get_proxy_dict(proxy_url)
        session.proxies.update(proxies)
    
    # Store the max_proxy_attempts for use in retry logic
    session._max_proxy_attempts = max_proxy_attempts
    
    # Override the request method to add auto-retry functionality
    original_request = session.request
    
    def request_with_retry(method, url, **kwargs):
        return make_request_with_auto_retry(
            method=method,
            url=url,
            session=session,
            max_proxy_attempts=max_proxy_attempts,
            **kwargs
        )
    
    session.request = request_with_retry
    return session


def enable_auto_retry_for_provider(provider_instance, max_proxy_attempts: int = 2):
    """
    Enable auto-retry functionality for an existing provider instance.
    
    This function can be used to add auto-retry functionality to providers
    that were created without it, or to update the max_proxy_attempts setting.
    
    Args:
        provider_instance: The provider instance to enable auto-retry for
        max_proxy_attempts: Maximum number of proxy attempts before falling back
    """
    # Set the max proxy attempts
    provider_instance._max_proxy_attempts = max_proxy_attempts
    
    # Get current proxies or empty dict
    current_proxies = getattr(provider_instance, 'proxies', {})
    
    # Patch all existing sessions
    _patch_instance_sessions(provider_instance, current_proxies)
    
    # Add helper methods if they don't exist
    if not hasattr(provider_instance, 'get_auto_retry_session'):
        _add_proxy_helpers(provider_instance, current_proxies)


def disable_auto_retry_for_provider(provider_instance):
    """
    Disable auto-retry functionality for a provider instance.
    
    This will restore the original request methods for all sessions.
    Note: This is a best-effort approach and may not work for all session types.
    
    Args:
        provider_instance: The provider instance to disable auto-retry for
    """
    for attr_name in dir(provider_instance):
        if attr_name.startswith('_'):
            continue
            
        try:
            attr_obj = getattr(provider_instance, attr_name)
            
            # Remove auto-retry from requests.Session objects
            if isinstance(attr_obj, requests.Session) and hasattr(attr_obj, '_auto_retry_patched'):
                # This is a simplified approach - in practice, restoring original methods
                # would require storing references to them, which we don't do here
                delattr(attr_obj, '_auto_retry_patched')
                
            # Similar for other session types
            elif httpx and isinstance(attr_obj, httpx.Client) and hasattr(attr_obj, '_auto_retry_patched'):
                delattr(attr_obj, '_auto_retry_patched')
                
            elif CurlSession and isinstance(attr_obj, CurlSession) and hasattr(attr_obj, '_auto_retry_patched'):
                delattr(attr_obj, '_auto_retry_patched')
                
            elif CurlAsyncSession and isinstance(attr_obj, CurlAsyncSession) and hasattr(attr_obj, '_auto_retry_patched'):
                delattr(attr_obj, '_auto_retry_patched')
                
        except Exception:
            continue


def proxy():
    """
    Return a working proxy dict or None. One-liner for easy use.
    Example:
        proxies = autoproxy.proxy()
        requests.get(url, proxies=proxies)
    """
    proxy_url = get_working_proxy()
    return get_proxy_dict(proxy_url) if proxy_url else None


def patch(obj, proxy_url=None):
    """
    Patch a function, class, or object to use proxies automatically.
    - For functions: inject proxies kwarg if not present.
    - For requests.Session: set .proxies.
    - For classes: patch all methods that look like HTTP calls.
    """
    proxy_dict = get_proxy_dict(proxy_url)
    if isinstance(obj, requests.Session):
        obj.proxies.update(proxy_dict)
        return obj
    if httpx and isinstance(obj, httpx.Client):
        obj._proxies = proxy_dict
        return obj
    if isinstance(obj, types.FunctionType):
        def wrapper(*args, **kwargs):
            if 'proxies' not in kwargs:
                kwargs['proxies'] = proxy_dict
            return obj(*args, **kwargs)
        return wrapper
    if isinstance(obj, type):  # class
        for attr in dir(obj):
            if attr.startswith('get') or attr.startswith('post'):
                method = getattr(obj, attr)
                if callable(method):
                    setattr(obj, attr, patch(method, proxy_url))
        return obj
    # fallback: return as is
    return obj


@contextmanager
def use_proxy(proxy_url=None):
    """
    Context manager to temporarily patch requests and httpx to use a proxy globally.
    Example:
        with autoproxy.use_proxy():
            requests.get(url)  # uses proxy automatically
    """
    proxy_dict = get_proxy_dict(proxy_url)
    orig_request = requests.Session.request
    def request_with_proxy(self, method, url, **kwargs):
        if 'proxies' not in kwargs:
            kwargs['proxies'] = proxy_dict
        return orig_request(self, method, url, **kwargs)
    requests.Session.request = request_with_proxy
    # Optionally patch httpx if available
    orig_httpx = None
    if httpx:
        orig_httpx = httpx.Client.request
        def httpx_request_with_proxy(self, method, url, **kwargs):
            if 'proxies' not in kwargs:
                kwargs['proxies'] = proxy_dict
            return orig_httpx(self, method, url, **kwargs)
        httpx.Client.request = httpx_request_with_proxy
    try:
        yield
    finally:
        requests.Session.request = orig_request
        if httpx and orig_httpx:
            httpx.Client.request = orig_httpx


def proxyify(func):
    """
    Decorator to auto-inject proxies into any function.
    Example:
        @autoproxy.proxyify
        def my_request(...): ...
    """
    proxy_dict = proxy()
    def wrapper(*args, **kwargs):
        if 'proxies' not in kwargs:
            kwargs['proxies'] = proxy_dict
        return func(*args, **kwargs)
    return wrapper


def list_proxies():
    """
    List all available proxies (remote only).
    """
    return get_cached_proxies()


def test_all_proxies(timeout=5):
    """
    Test all proxies and return a dict of proxy_url: True/False.
    """
    results = {}
    for proxy in get_cached_proxies():
        results[proxy] = test_proxy(proxy, timeout=timeout)
    return results


def current_proxy():
    """
    Return a random proxy that would be used now (Webshare preferred).
    """
    return get_auto_proxy()