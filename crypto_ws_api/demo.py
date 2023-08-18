#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import aiohttp
import asyncio
import shortuuid
import logging
import toml
import contextlib

from crypto_ws_api import CONFIG_FILE
from crypto_ws_api.ws_session import UserWSSession


logger = logging.getLogger(__name__)
formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
#
sh = logging.StreamHandler()
sh.setFormatter(formatter)
sh.setLevel(logging.DEBUG)
#
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(sh)


async def main(account_name):
    # Get credentials and create user session
    # Can be omitted if you have credentials from other source
    exchange, _test_net, api_key, api_secret, passphrase, ws_api_endpoint = get_credentials(account_name)

    session = aiohttp.ClientSession()

    trade_id = shortuuid.uuid()

    user_session = UserWSSession(
        session,
        exchange,
        ws_api_endpoint,
        api_key,
        api_secret,
        passphrase
    )

    # Demo method's calling
    await account_information(user_session, trade_id)
    asyncio.ensure_future(demo_loop(user_session, get_time, trade_id, 2))
    asyncio.ensure_future(demo_loop(user_session, current_average_price, trade_id, 3))

    await asyncio.sleep(12)

    # Stop user session and close aiohttp session
    await user_session.stop()
    await session.close()


async def demo_loop(_session, _method, _trade_id, delay):
    for _ in range(60):
        await _method(_session, _trade_id)
        await asyncio.sleep(delay)


async def get_time(user_session: UserWSSession, _trade_id):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#check-server-time
    try:
        res = await user_session.handle_request(
                _trade_id,
                "time",
            )
        if res is None:
            logger.warning("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        logger.error("Handling exception: %s",_ex)
    else:
        logger.info("Check server time response: %s", res)


async def current_average_price(user_session: UserWSSession, _trade_id):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#current-average-price
    try:
        params = {
            "symbol": "BNBBTC",
        }
        res = await user_session.handle_request(
            _trade_id,
            "avgPrice",
            params,
        )
        if res is None:
            logger.warning("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        logger.error("Handling exception: %s",_ex)
    else:
        logger.info("Current average price response: %s",res)


async def account_information(user_session: UserWSSession, _trade_id):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#account-information-user_data
    try:
        res = await user_session.handle_request(
            _trade_id,
            "account.status",
            _api_key=True,
            _signed=True
        )
        if res is None:
            logger.warning("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        logger.error("Handling exception: %s",_ex)
    else:
        logger.info("Account information (USER_DATA) response: %s", res)


def get_credentials(_account_name: str) -> ():
    config = toml.load(str(CONFIG_FILE))
    accounts = config.get('accounts')
    for account in accounts:
        if account.get('name') == _account_name:
            return _get_credentials(account, config)
    raise UserWarning(f"Can't find account '{_account_name}' defined in {CONFIG_FILE}")


def _get_credentials(account, config):
    exchange = account['exchange']
    test_net = account['test_net']
    #
    api_key = account['api_key']
    api_secret = account['api_secret']
    passphrase = account.get('passphrase')
    #
    endpoint = config['endpoint'][exchange]
    #
    ws_api = endpoint.get('ws_api_test') if test_net else endpoint.get('ws_api')
    #
    return exchange, test_net, api_key, api_secret, passphrase, ws_api


if __name__ == '__main__':
    logger.info("INFO logging message from demo.main()")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main('Demo - Binance'))
