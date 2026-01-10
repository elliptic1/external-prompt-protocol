"""
FastAPI server for EPP Inbox.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ..crypto.keys import KeyPair
from ..executors.base import Executor
from ..executors.file_queue import FileQueueExecutor
from ..executors.logger import LoggerExecutor
from ..executors.noop import NoOpExecutor
from ..policy.nonce_registry import NonceRegistry
from ..policy.rate_limiter import RateLimiter
from ..policy.trust_registry import TrustRegistry
from .processor import InboxProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class InboxServer:
    """EPP Inbox FastAPI server."""

    def __init__(self, config_path: str = ".epp-inbox/config.yaml"):
        """
        Initialize inbox server.

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self.app = FastAPI(
            title="EPP Inbox",
            description="External Prompt Protocol Inbox Service",
            version="1.0.0",
        )

        # Initialize components
        self._init_components()

        # Setup routes
        self._setup_routes()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_file = Path(config_path)

        if not config_file.exists():
            # Create default configuration
            default_config = {
                "inbox": {
                    "host": "0.0.0.0",
                    "port": 8000,
                    "data_dir": ".epp-inbox/data",
                },
                "keys": {
                    "private_key_path": ".epp-inbox/inbox.key",
                    "public_key_path": ".epp-inbox/inbox.pub",
                },
                "storage": {
                    "trust_registry": ".epp-inbox/data/trust_registry.json",
                },
                "executor": {
                    "type": "file_queue",
                    "queue_dir": ".epp-inbox/data/queue",
                },
            }

            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w") as f:
                yaml.dump(default_config, f, default_flow_style=False)

            logger.info(f"Created default configuration at {config_path}")
            return default_config

        with open(config_file, "r") as f:
            return yaml.safe_load(f)

    def _init_components(self) -> None:
        """Initialize inbox components."""
        # Load or generate keys
        private_key_path = self.config["keys"]["private_key_path"]
        public_key_path = self.config["keys"]["public_key_path"]

        if os.path.exists(private_key_path):
            logger.info(f"Loading inbox keys from {private_key_path}")
            self.key_pair = KeyPair.load_from_file(private_key_path)
        else:
            logger.info("Generating new inbox key pair")
            self.key_pair = KeyPair.generate()
            Path(private_key_path).parent.mkdir(parents=True, exist_ok=True)
            self.key_pair.save_to_files(private_key_path, public_key_path)
            logger.info(f"Saved inbox keys to {private_key_path} and {public_key_path}")

        logger.info(f"Inbox public key: {self.key_pair.public_key_hex()}")

        # Initialize trust registry
        trust_registry_path = self.config["storage"]["trust_registry"]
        self.trust_registry = TrustRegistry(storage_path=trust_registry_path)
        logger.info(
            f"Loaded trust registry with {len(self.trust_registry.trusted_senders)} "
            "trusted senders"
        )

        # Initialize nonce registry
        self.nonce_registry = NonceRegistry()

        # Initialize rate limiter
        self.rate_limiter = RateLimiter()

        # Initialize executor
        self.executor = self._create_executor()
        logger.info(f"Initialized executor: {self.executor.name()}")

        # Initialize processor
        self.processor = InboxProcessor(
            recipient_public_key_hex=self.key_pair.public_key_hex(),
            trust_registry=self.trust_registry,
            nonce_registry=self.nonce_registry,
            rate_limiter=self.rate_limiter,
            executor=self.executor,
        )

    def _create_executor(self) -> Executor:
        """Create executor based on configuration."""
        executor_config = self.config.get("executor", {})
        executor_type = executor_config.get("type", "noop")

        if executor_type == "noop":
            return NoOpExecutor()
        elif executor_type == "file_queue":
            queue_dir = executor_config.get("queue_dir", ".epp-inbox/data/queue")
            return FileQueueExecutor(queue_dir=queue_dir)
        elif executor_type == "logger":
            log_file = executor_config.get("log_file", ".epp-inbox/data/envelopes.log")
            return LoggerExecutor(log_file=log_file)
        else:
            raise ValueError(f"Unknown executor type: {executor_type}")

    def _setup_routes(self) -> None:
        """Setup FastAPI routes."""

        @self.app.get("/")
        async def root() -> Dict[str, Any]:
            """Root endpoint with inbox information."""
            return {
                "service": "EPP Inbox",
                "version": "1.0.0",
                "protocol_version": "1",
                "public_key": self.key_pair.public_key_hex(),
                "endpoints": {
                    "submit": "/epp/v1/submit",
                    "health": "/health",
                    "info": "/",
                },
            }

        @self.app.get("/health")
        async def health() -> Dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy"}

        @self.app.post("/epp/v1/submit")
        async def submit_envelope(request: Request) -> JSONResponse:
            """
            Submit an EPP envelope for processing.

            Returns success or error receipt.
            """
            try:
                envelope_data = await request.json()
            except Exception as e:
                logger.warning(f"Invalid JSON: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON")

            # Process envelope
            receipt = self.processor.process_envelope(envelope_data)

            # Determine HTTP status code based on receipt
            if receipt.status == "accepted":
                status_code = 200
            elif hasattr(receipt, "error"):
                error_code = receipt.error.code
                if error_code in ["INVALID_FORMAT", "UNSUPPORTED_VERSION"]:
                    status_code = 400
                elif error_code in ["INVALID_SIGNATURE", "UNTRUSTED_SENDER"]:
                    status_code = 401
                elif error_code in ["POLICY_DENIED", "WRONG_RECIPIENT"]:
                    status_code = 403
                elif error_code == "RATE_LIMITED":
                    status_code = 429
                else:
                    status_code = 400
            else:
                status_code = 400

            return JSONResponse(
                status_code=status_code,
                content=receipt.model_dump(),
            )

    def run(self) -> None:
        """Run the inbox server."""
        host = self.config["inbox"]["host"]
        port = self.config["inbox"]["port"]

        logger.info(f"Starting EPP Inbox on {host}:{port}")
        logger.info(f"Submit endpoint: http://{host}:{port}/epp/v1/submit")

        uvicorn.run(self.app, host=host, port=port)


def main() -> None:
    """Main entry point for inbox server."""
    import argparse

    parser = argparse.ArgumentParser(description="EPP Inbox Server")
    parser.add_argument(
        "--config",
        default=".epp-inbox/config.yaml",
        help="Path to configuration file",
    )
    args = parser.parse_args()

    server = InboxServer(config_path=args.config)
    server.run()


if __name__ == "__main__":
    main()
