import random
import requests
import functools
import time
from contextlib import contextmanager
from .static_proxies import STATIC_WEBSHARE_PROXIES, STATIC_NORDVPN_PROXIES, ALL_STATIC_PROXIES
from abc import ABCMeta
import types
import threading
from typing import Dict, List, Optional, Any, Callable, Union

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

PROXY_SOURCE_URL = "http://207.180.209.185:5000/ips.txt"

class LitMeta(ABCMeta):
    """
    Metaclass to ensure all subclasses automatically get proxy support and inbuilt auto-retry for HTTP sessions.
    This will inject proxies and auto-retry into any requests.Session, httpx.Client, or curl_cffi session attributes found on the instance.
    To disable automatic proxy injection, set disable_auto_proxy=True in the constructor or
    set the class attribute DISABLE_AUTO_PROXY = True.
    """
    def __call__(cls, *args, **kwargs):
        instance = super().__call__(*args, **kwargs)
        disable_auto_proxy = kwargs.get('disable_auto_proxy', False) or getattr(cls, 'DISABLE_AUTO_PROXY', False)
        proxies = getattr(instance, 'proxies', None) or kwargs.get('proxies', None)
        if proxies is None and not disable_auto_proxy:
            proxies = LitProxy.proxy()
        elif proxies is None:
            proxies = {}
        instance.proxies = proxies
        if not hasattr(instance, '_max_proxy_attempts'):
            instance._max_proxy_attempts = kwargs.get('max_proxy_attempts', 2)
        LitMeta._patch_instance_sessions(instance, proxies)
        LitMeta._add_proxy_helpers(instance, proxies)
        return instance

    @staticmethod
    def _patch_instance_sessions(instance, proxies):
        """Patch existing session objects on the instance with proxy configuration and auto-retry functionality."""
        for attr_name in dir(instance):
            if attr_name.startswith('_'):
                continue
            try:
                attr_obj = getattr(instance, attr_name)
                
                # Patch requests.Session objects
                if isinstance(attr_obj, requests.Session):
                    if proxies:
                        attr_obj.proxies.update(proxies)
                    LitProxy._add_auto_retry_to_session(attr_obj, instance)
                
                # Patch httpx.Client objects
                elif httpx and isinstance(attr_obj, httpx.Client):
                    try:
                        # httpx uses different proxy format
                        if proxies:
                            attr_obj._proxies = proxies
                        LitProxy._add_auto_retry_to_httpx_client(attr_obj, instance)
                    except Exception:
                        pass
                
                # Patch curl_cffi Session objects
                elif CurlSession and isinstance(attr_obj, CurlSession):
                    try:
                        if proxies:
                            attr_obj.proxies.update(proxies)
                        LitProxy._add_auto_retry_to_curl_session(attr_obj, instance)
                    except Exception:
                        pass
                
                # Patch curl_cffi AsyncSession objects
                elif CurlAsyncSession and isinstance(attr_obj, CurlAsyncSession):
                    try:
                        if proxies:
                            attr_obj.proxies.update(proxies)
                        LitProxy._add_auto_retry_to_curl_async_session(attr_obj, instance)
                    except Exception:
                        pass
                        
            except Exception:
                continue

    @staticmethod
    def _add_proxy_helpers(instance, proxies):
        """Add helper methods to the instance for creating proxied sessions."""
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
                
        def get_auto_retry_session(max_proxy_attempts=2):
            """Get a requests.Session with automatic proxy retry and fallback functionality"""
            return LitProxy.create_auto_retry_session(max_proxy_attempts)
            
        def make_auto_retry_request(method, url, max_proxy_attempts=2, **kwargs):
            """Make a request with automatic proxy retry and fallback"""
            return LitProxy.make_request_with_auto_retry(
                method=method,
                url=url,
                max_proxy_attempts=max_proxy_attempts,
                **kwargs
            )
            
        def patch_session_with_auto_retry(session_obj):
            """Patch any session object with auto-retry functionality"""
            if isinstance(session_obj, requests.Session):
                LitProxy._add_auto_retry_to_session(session_obj, instance)
            elif httpx and isinstance(session_obj, httpx.Client):
                LitProxy._add_auto_retry_to_httpx_client(session_obj, instance)
            elif CurlSession and isinstance(session_obj, CurlSession):
                LitProxy._add_auto_retry_to_curl_session(session_obj, instance)
            elif CurlAsyncSession and isinstance(session_obj, CurlAsyncSession):
                LitProxy._add_auto_retry_to_curl_async_session(session_obj, instance)
            return session_obj
            
        # Add methods to instance
        instance.get_proxied_session = get_proxied_session
        instance.get_proxied_httpx_client = get_proxied_httpx_client
        instance.get_proxied_curl_session = get_proxied_curl_session
        instance.get_proxied_curl_async_session = get_proxied_curl_async_session
        instance.get_auto_retry_session = get_auto_retry_session
        instance.make_auto_retry_request = make_auto_retry_request
        instance.patch_session_with_auto_retry = patch_session_with_auto_retry

class LitProxy:
    """
    LitProxy: Easy, modern proxy rotation and patching for Python HTTP clients.
    """
    _proxy_cache = {
        'proxies': [],
        'last_updated': 0,
        'cache_duration': 300,  # 5 minutes
        'refreshing': False
    }

    @staticmethod
    def proxy():
        """Get a working proxy dict (Webshare preferred)."""
        proxy_url = LitProxy.get_working_proxy()
        return LitProxy.get_proxy_dict(proxy_url) if proxy_url else None

    @staticmethod
    def get_proxy_dict(proxy_url=None):
        if proxy_url is None:
            proxy_url = LitProxy.get_auto_proxy()
        if proxy_url is None:
            return {}
        return {'http': proxy_url, 'https': proxy_url}

    @staticmethod
    def _background_refresh():
        cache = LitProxy._proxy_cache
        if cache['refreshing']:
            return
        cache['refreshing'] = True
        try:
            new_proxies = LitProxy.fetch_proxies()
            if new_proxies:
                cache['proxies'] = new_proxies
                cache['last_updated'] = time.time()
        finally:
            cache['refreshing'] = False

    @staticmethod
    def get_cached_proxies():
        """Get proxies from cache or trigger background fetch if cache is expired.
        No priority or preferred order; returns all available proxies in random order."""
        current_time = time.time()
        cache = LitProxy._proxy_cache
        if (current_time - cache['last_updated'] > cache['cache_duration'] or not cache['proxies']):
            # Start background refresh if not already running
            if not cache.get('refreshing', False):
                threading.Thread(target=LitProxy._background_refresh, daemon=True).start()
        # Combine all proxies and shuffle
        proxies = STATIC_WEBSHARE_PROXIES + cache['proxies'] + STATIC_NORDVPN_PROXIES
        proxies = list(dict.fromkeys(proxies))  # Remove duplicates, preserve order
        random.shuffle(proxies)
        return proxies

    @staticmethod
    def get_auto_proxy():
        """Return a random proxy from all available proxies, no preference."""
        proxies = LitProxy.get_cached_proxies()
        if proxies:
            return random.choice(proxies)
        return None

    @staticmethod
    def get_working_proxy(max_attempts=5, timeout=10):
        """Return a working proxy, randomly selected from all available proxies."""
        proxies = LitProxy.get_cached_proxies()
        if not proxies:
            return None
        test_proxies = random.sample(proxies, min(max_attempts, len(proxies)))
        for proxy in test_proxies:
            if LitProxy.test_proxy(proxy, timeout):
                return proxy
        return None

    @staticmethod
    def test_proxy(proxy_url, timeout=10):
        try:
            test_url = "https://httpbin.org/ip"
            proxies = {'http': proxy_url, 'https': proxy_url}
            response = requests.get(test_url, proxies=proxies, timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def fetch_proxies():
        """Fetch proxy list from the remote source."""
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

    @staticmethod
    def get_proxy_stats():
        cache = LitProxy._proxy_cache
        return {
            'proxy_count': len(cache['proxies']),
            'last_updated': cache['last_updated'],
            'cache_duration': cache['cache_duration'],
            'cache_age_seconds': time.time() - cache['last_updated'],
            'source_url': PROXY_SOURCE_URL
        }

    @staticmethod
    def set_proxy_cache_duration(duration):
        LitProxy._proxy_cache['cache_duration'] = duration

    @staticmethod
    def get_proxied_session(proxy_url=None):
        session = requests.Session()
        session.proxies.update(LitProxy.get_proxy_dict(proxy_url))
        return session

    @staticmethod
    def get_proxied_httpx_client(proxy_url=None, **kwargs):
        if httpx:
            return httpx.Client(proxies=LitProxy.get_proxy_dict(proxy_url), **kwargs)
        else:
            raise ImportError("httpx is not installed")

    @staticmethod
    def get_proxied_curl_session(proxy_url=None, impersonate="chrome120", **kwargs):
        if CurlSession:
            return CurlSession(proxies=LitProxy.get_proxy_dict(proxy_url), impersonate=impersonate, **kwargs)
        else:
            raise ImportError("curl_cffi is not installed")

    @staticmethod
    def get_proxied_curl_async_session(proxy_url=None, impersonate="chrome120", **kwargs):
        if CurlAsyncSession:
            return CurlAsyncSession(proxies=LitProxy.get_proxy_dict(proxy_url), impersonate=impersonate, **kwargs)
        else:
            raise ImportError("curl_cffi is not installed")

    @staticmethod
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
                    new_proxy_url = LitProxy.get_auto_proxy()
                    if new_proxy_url:
                        new_proxies = LitProxy.get_proxy_dict(new_proxy_url)
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

    @staticmethod
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
        proxy_url = LitProxy.get_auto_proxy()
        if proxy_url:
            proxies = LitProxy.get_proxy_dict(proxy_url)
            session.proxies.update(proxies)
        
        # Store the max_proxy_attempts for use in retry logic
        session._max_proxy_attempts = max_proxy_attempts
        
        # Override the request method to add auto-retry functionality
        original_request = session.request
        
        def request_with_retry(method, url, **kwargs):
            return LitProxy.make_request_with_auto_retry(
                method=method,
                url=url,
                session=session,
                max_proxy_attempts=max_proxy_attempts,
                **kwargs
            )
        
        session.request = request_with_retry
        return session

    @staticmethod
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
                                new_proxy_url = LitProxy.get_auto_proxy()
                                if new_proxy_url:
                                    new_proxies = LitProxy.get_proxy_dict(new_proxy_url)
                                    instance.proxies = new_proxies
                                    
                                    # Update any existing sessions with new proxy
                                    LitMeta._patch_instance_sessions(instance, new_proxies)
                                    
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
                            LitMeta._patch_instance_sessions(instance, {})
                            return func(*args, **kwargs)
                        except Exception:
                            # Restore original proxy settings and re-raise the first error
                            instance.proxies = original_proxies
                            LitMeta._patch_instance_sessions(instance, original_proxies)
                            raise first_error
                    else:
                        # No proxies were configured, just re-raise the original error
                        raise first_error
                        
            return wrapper
        return decorator

    @staticmethod
    def patch(obj, proxy_url=None):
        """
        Patch a function, class, or object to use proxies automatically.
        - For functions: inject proxies kwarg if not present.
        - For requests.Session: set .proxies.
        - For classes: patch all methods that look like HTTP calls.
        """
        if isinstance(obj, requests.Session):
            obj.proxies.update(LitProxy.get_proxy_dict(proxy_url))
            return obj
        if httpx and isinstance(obj, httpx.Client):
            obj._proxies = LitProxy.get_proxy_dict(proxy_url)
            return obj
        if isinstance(obj, types.FunctionType):
            def wrapper(*args, **kwargs):
                if 'proxies' not in kwargs:
                    kwargs['proxies'] = LitProxy.get_proxy_dict(proxy_url)
                return obj(*args, **kwargs)
            return wrapper
        if isinstance(obj, type):  # class
            for attr in dir(obj):
                if attr.startswith('get') or attr.startswith('post'):
                    method = getattr(obj, attr)
                    if callable(method):
                        setattr(obj, attr, LitProxy.patch(method, proxy_url))
            return obj
        # fallback: return as is
        return obj

    @staticmethod
    @contextmanager
    def use_proxy(proxy_url=None):
        """
        Context manager to temporarily patch requests and httpx to use a proxy globally.
        Example:
            with LitProxy.use_proxy():
                requests.get(url)  # uses proxy automatically
        """
        orig_request = requests.Session.request
        def request_with_proxy(self, method, url, **kwargs):
            if 'proxies' not in kwargs:
                kwargs['proxies'] = LitProxy.get_proxy_dict(proxy_url)
            return orig_request(self, method, url, **kwargs)
        requests.Session.request = request_with_proxy
        
        # Optionally patch httpx if available
        orig_httpx = None
        if httpx:
            orig_httpx = httpx.Client.request
            def httpx_request_with_proxy(self, method, url, **kwargs):
                if 'proxies' not in kwargs:
                    kwargs['proxies'] = LitProxy.get_proxy_dict(proxy_url)
                return orig_httpx(self, method, url, **kwargs)
            httpx.Client.request = httpx_request_with_proxy
            
        try:
            yield
        finally:
            requests.Session.request = orig_request
            if httpx and orig_httpx:
                httpx.Client.request = orig_httpx

    @staticmethod
    def proxyify(func):
        """
        Decorator to auto-inject proxies into any function.
        Example:
            @LitProxy.proxyify
            def my_request(...): ...
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if 'proxies' not in kwargs:
                kwargs['proxies'] = LitProxy.proxy()
            return func(*args, **kwargs)
        return wrapper

    @staticmethod
    def test_all_proxies(timeout=5):
        results = {}
        for proxy in LitProxy.list_proxies():
            results[proxy] = LitProxy.test_proxy(proxy, timeout=timeout)
        return results

    @staticmethod
    def current_proxy():
        return LitProxy.get_auto_proxy()

    @staticmethod
    def list_proxies():
        """List all available proxies in random order (no preference)."""
        proxies = LitProxy.get_cached_proxies()
        random.shuffle(proxies)
        return proxies

    @staticmethod
    def refresh_proxy_cache():
        """Force refresh the proxy cache. Returns number of proxies loaded."""
        cache = LitProxy._proxy_cache
        cache['last_updated'] = 0  # Force refresh
        proxies = LitProxy.get_cached_proxies()
        return len(proxies)

    @staticmethod
    def enable_auto_retry_for_provider(provider_instance, max_proxy_attempts=2):
        """Enable auto-retry functionality for an existing provider instance."""
        provider_instance._max_proxy_attempts = max_proxy_attempts
        current_proxies = getattr(provider_instance, 'proxies', {})
        LitMeta._patch_instance_sessions(provider_instance, current_proxies)
        if not hasattr(provider_instance, 'get_auto_retry_session'):
            LitMeta._add_proxy_helpers(provider_instance, current_proxies)

    @staticmethod
    def disable_auto_retry_for_provider(provider_instance):
        """Disable auto-retry functionality for a provider instance."""
        for attr_name in dir(provider_instance):
            if attr_name.startswith('_'):
                continue
            try:
                attr_obj = getattr(provider_instance, attr_name)
                if isinstance(attr_obj, requests.Session) and hasattr(attr_obj, '_auto_retry_patched'):
                    delattr(attr_obj, '_auto_retry_patched')
                elif httpx and isinstance(attr_obj, httpx.Client) and hasattr(attr_obj, '_auto_retry_patched'):
                    delattr(attr_obj, '_auto_retry_patched')
                elif CurlSession and isinstance(attr_obj, CurlSession) and hasattr(attr_obj, '_auto_retry_patched'):
                    delattr(attr_obj, '_auto_retry_patched')
                elif CurlAsyncSession and isinstance(attr_obj, CurlAsyncSession) and hasattr(attr_obj, '_auto_retry_patched'):
                    delattr(attr_obj, '_auto_retry_patched')
            except Exception:
                continue

    @staticmethod
    def _add_auto_retry_to_session(session: requests.Session, instance: Any) -> None:
        """Add enhanced auto-retry functionality to a requests.Session object."""
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
                        new_proxy_url = LitProxy.get_auto_proxy()
                        if new_proxy_url:
                            new_proxies = LitProxy.get_proxy_dict(new_proxy_url)
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

    @staticmethod
    def _add_auto_retry_to_httpx_client(client, instance: Any) -> None:
        """Add enhanced auto-retry functionality to an httpx.Client object."""
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
                            new_proxy_url = LitProxy.get_auto_proxy()
                            if new_proxy_url:
                                new_proxies = LitProxy.get_proxy_dict(new_proxy_url)
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

    @staticmethod
    def _add_auto_retry_to_curl_session(session, instance: Any) -> None:
        """Add enhanced auto-retry functionality to a curl_cffi.Session object."""
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
                            new_proxy_url = LitProxy.get_auto_proxy()
                            if new_proxy_url:
                                new_proxies = LitProxy.get_proxy_dict(new_proxy_url)
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

    @staticmethod
    def _add_auto_retry_to_curl_async_session(session, instance: Any) -> None:
        """Add enhanced auto-retry functionality to a curl_cffi.AsyncSession object."""
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
                            new_proxy_url = LitProxy.get_auto_proxy()
                            if new_proxy_url:
                                new_proxies = LitProxy.get_proxy_dict(new_proxy_url)
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
