#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crypto WS API connector for ASYNC requests
https://developers.binance.com/docs/binance-trading-api/websocket_api#general-api-information
Provides methods of connection management, keepalive and rate limits control
Full coverage of all methods provided by the interface
For crypto exchanges: +Binance, -OKX, -Bitfinex,
"""
__authors__ = ["Jerry Fedorenko"]
__license__ = "MIT"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
__email__ = "jerry.fedorenko@yahoo.com"
__credits__ = ["https://github.com/DanyaSWorlD"]
__version__ = "2.0.0b2"

from pathlib import Path
import shutil
from platformdirs import user_config_path


TIMEOUT = 10  # sec timeout for WSS receive
ID_LEN_LIMIT = {
    "binance": 36,
    "okx": 32
}

CONFIG_PATH = user_config_path("crypto_ws_api")
CONFIG_FILE = Path(CONFIG_PATH, "ws_api.toml")


def init():
    if CONFIG_FILE.exists():
        print(f"Config found at {CONFIG_FILE}")
    else:
        print("Can't find config file! Creating it...")
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(Path(__file__).parent.absolute(), "ws_api.toml.template"), CONFIG_FILE)
        print(f"Before first run set account(s) API key into {CONFIG_FILE}")
        raise SystemExit(1)


if __name__ == '__main__':
    init()
