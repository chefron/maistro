import threading
import time
import random
from typing import Callable, TypeVar, Generic

T = TypeVar('T')  # Type variable for return values

class TwitterError(Exception):
    """Exception for Twitter-related errors."""
    pass

class RequestQueue:
    """
    Queue for managing Twitter API requests with natural delays and rate limiting
    to mimic human behavior and avoid detection.
    """
    
    def __init__(self):
        self.queue = []
        self.processing = False
        self.lock = threading.Lock()
        # Configurable delay ranges (in seconds)
        self.min_delay = 1.5
        self.max_delay = 3.5
        # For tracking consecutive errors
        self.consecutive_errors = 0
        self.max_retries = 3
    
    def add(self, request_func: Callable[[], T]) -> T:
        """
        Add a request function to the queue and process it when ready.
        
        Args:
            request_func: A callable function that performs the API request
            
        Returns:
            The result of the request function
        """
        result = None
        error = None
        completed = threading.Event()
        
        def execute_request():
            nonlocal result, error
            try:
                result = request_func()
            except Exception as e:
                error = e
            finally:
                completed.set()
        
        # Add to queue
        with self.lock:
            self.queue.append(execute_request)
            # Start processing if not already running
            if not self.processing:
                threading.Thread(target=self._process_queue).start()
        
        # Wait for completion
        completed.wait()
        
        if error:
            raise error
        return result
    
    def _process_queue(self):
        """Process queued requests with natural delays between them."""
        with self.lock:
            if self.processing:
                return
            self.processing = True
        
        try:
            while True:
                # Get next request
                with self.lock:
                    if not self.queue:
                        self.processing = False
                        break
                    request = self.queue.pop(0)
                
                # Execute with retry logic
                self._execute_with_retry(request)
                
                # Add natural delay between requests
                self._add_natural_delay()
                
        except Exception as e:
            print(f"Error in request queue processing: {e}")
            with self.lock:
                self.processing = False
    
    def _execute_with_retry(self, request_func):
        """Execute a request with retry logic for transient errors."""
        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                request_func()
                # Reset error counter on success
                self.consecutive_errors = 0
                return
            except Exception as e:
                retry_count += 1
                self.consecutive_errors += 1
                
                if retry_count <= self.max_retries:
                    # Exponential backoff with jitter
                    backoff_time = (2 ** retry_count) * random.uniform(0.8, 1.2)
                    print(f"Request failed, retrying in {backoff_time:.2f} seconds... ({e})")
                    time.sleep(backoff_time)
                else:
                    print(f"Request failed after {self.max_retries} retries: {e}")
                    raise
    
    def _add_natural_delay(self):
        """Add a natural, human-like delay between requests."""
        # Base delay
        base_delay = random.uniform(self.min_delay, self.max_delay)
        
        # Add extra delay if we've had errors (to avoid aggressive retries)
        error_factor = min(self.consecutive_errors * 0.5, 5.0)  # Cap at 5 seconds extra
        
        # Add occasional longer pauses (10% chance of "thinking")
        if random.random() < 0.1:
            thinking_pause = random.uniform(2.0, 8.0)
        else:
            thinking_pause = 0
        
        total_delay = base_delay + error_factor + thinking_pause
        
        # Log only if delay is significant
        if total_delay > self.min_delay * 1.5:
            print(f"Adding delay of {total_delay:.2f} seconds between requests...")
        
        time.sleep(total_delay)