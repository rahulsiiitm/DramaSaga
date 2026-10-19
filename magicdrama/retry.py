import time

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

def call_with_retries(fn, max_attempts=3, base_delay=1.0, sleep=None):
    sleep = sleep or time.sleep
    for attempt in range(1, max_attempts + 1):
        try:
            resp = fn()
            if getattr(resp, "status_code", 200) in RETRYABLE_STATUS and attempt < max_attempts:
                sleep(base_delay * (2 ** (attempt - 1)))
                continue
            return resp
        except RetryableStatusError as e:
            if attempt < max_attempts:
                sleep(base_delay * (2 ** (attempt - 1)))
                continue
            if e.response is not None:
                e.response.raise_for_status()
            raise
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
            if attempt < max_attempts:
                sleep(base_delay * (2 ** (attempt - 1)))
                continue
            raise


class RetryableStatusError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response
        self.status_code = getattr(response, "status_code", None)

