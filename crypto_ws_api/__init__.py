#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crypto WS API connector for ASYNC requests
https://developers.binance.com/docs/binance-trading-api/websocket_api#general-api-information
Provides methods of connection management, keepalive and rate limits control
Full coverage of all methods provided by the interface
For crypto exchanges: Binance, OKX, Bitfinex,
"""
__authors__ = ["Jerry Fedorenko"]
__license__ = "MIT"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
__email__ = "jerry.fedorenko@yahoo.com"
__credits__ = ["https://github.com/DanyaSWorlD"]
__version__ = "2.1.0"

from pathlib import Path
import shutil
from platformdirs import user_config_path

VERSION = __version__
TIMEOUT = 5  # sec timeout for WSS initialization and get response
DELAY = 0.1  # sec delay in keepalive loop
DEBUG_LOG = 'debug'  # The name of the exchange for which log files, separated by trade_id with DEBUG level, will be generated
# Maximum str size for unique query ID
ID_LEN_LIMIT = {
    "binance": 36,
    "okx": 32,
    "bitfinex": 32,
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
