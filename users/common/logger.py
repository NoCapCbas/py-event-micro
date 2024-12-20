import time
import logging
from typing import Callable
from fastapi import Request, Response
from datetime import datetime
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class LoggerMiddleware:
    def __init__(self, app_name: str = "FastAPI"):
        self.logger = logging.getLogger(app_name)
        self.logger.setLevel(logging.INFO)

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Start timer
        start_time = time.time()
        
        # Get request details
        request_id = request.headers.get('X-Request-ID', str(time.time()))
        
        # Log request
        self.logger.info(
            json.dumps({
                "request_id": request_id,
                "type": "request",
                "timestamp": datetime.now().isoformat(),
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "client_ip": request.client.host,
                "path_params": request.path_params,
            })
        )

        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response
            self.logger.info(
                json.dumps({
                    "request_id": request_id,
                    "type": "response",
                    "timestamp": datetime.now().isoformat(),
                    "duration": f"{duration:.3f}s",
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                })
            )

            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{duration:.3f}s"
            
            return response

        except Exception as e:
            # Log error
            self.logger.error(
                json.dumps({
                    "request_id": request_id,
                    "type": "error",
                    "timestamp": datetime.now().isoformat(),
                    "duration": f"{time.time() - start_time:.3f}s",
                    "error": str(e),
                    "error_type": type(e).__name__,
                })
            )
            raise
