"""
Zep API 重试工具类
提供统一的装饰器和包装函数，用于处理 Zep Cloud 的限流 (429) 和网络错误
"""

import time
import functools
from typing import Callable, Any, TypeVar, Optional
from zep_cloud import InternalServerError, ApiError

from .logger import get_logger

logger = get_logger('mirofish.zep_retry')

T = TypeVar('T')

def zep_retry(
    max_retries: int = 5,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    operation_name: Optional[str] = None
):
    """
    Zep API 调用的重试装饰器
    支持处理 429 (Rate Limit), 500 (Internal Server Error) 以及网络异常
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            name = operation_name or func.__name__
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (InternalServerError, ConnectionError, TimeoutError, OSError) as e:
                    last_exception = e
                    status_code = getattr(e, 'status_code', 500)
                    error_msg = str(e)[:150]
                    
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Zep {name} 尝试 {attempt + 1} 失败 (Code: {status_code}): {error_msg}. "
                            f"{delay:.1f}秒后重试..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"Zep {name} 在 {max_retries} 次尝试后最终失败: {error_msg}")
                        raise
                        
                except ApiError as e:
                    last_exception = e
                    status_code = e.status_code
                    error_msg = str(e)[:150]
                    
                    # 特别处理 429 限流
                    if status_code == 429:
                        if attempt < max_retries - 1:
                            # 尝试从 header 获取 retry-after
                            retry_after = 0
                            if e.headers and 'retry-after' in e.headers:
                                try:
                                    retry_after = float(e.headers['retry-after'])
                                except ValueError:
                                    pass
                            
                            current_delay = max(delay, retry_after)
                            logger.warning(
                                f"Zep {name} 遭遇限流 (429). {current_delay:.1f}秒后重试... (尝试 {attempt + 1}/{max_retries})"
                            )
                            time.sleep(current_delay)
                            delay *= backoff_factor
                            continue
                        else:
                            logger.error(f"Zep {name} 连续限流，尝试次数耗尽")
                            raise
                    
                    # 其他 ApiError (如 400, 401 等) 通常不建议直接重试，直接抛出
                    raise
                except Exception as e:
                    # 未知异常不自动重试
                    logger.error(f"Zep {name} 遭遇未知异常: {str(e)}")
                    raise e
                    
            return func(*args, **kwargs) # Should not reach here if max_retries > 0
        return wrapper
    return decorator

def call_with_retry(
    func: Callable[..., T],
    *args,
    max_retries: int = 5,
    initial_delay: float = 2.0,
    operation_name: str = "API Call",
    **kwargs
) -> T:
    """封装版的重试调用函数，方便 lambda 使用"""
    decorated = zep_retry(
        max_retries=max_retries, 
        initial_delay=initial_delay, 
        operation_name=operation_name
    )(func)
    return decorated(*args, **kwargs)
