"""Entry point for running the Tiro server."""

import logging

import uvicorn

from tiro.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    config = load_config()

    # Import here so config is loaded before app creation
    from tiro.app import create_app

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
