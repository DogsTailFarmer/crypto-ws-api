#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import aiohttp
import asyncio
import shortuuid
import logging.handlers

from crypto_ws_api.ws_session import get_credentials, UserWSSession


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

    # Can be omitted if you have credentials
    exchange, _test_net, api_key, api_secret, passphrase, ws_api_endpoint = get_credentials(account_name)

    session = aiohttp.ClientSession()
    trade_id = shortuuid.uuid()

    user_session = UserWSSession(
        exchange,
        api_key,
        api_secret,
        endpoint=ws_api_endpoint,
        session=session,
    )

    # Demo method's calling
    await account_information(user_session, trade_id)
    asyncio.ensure_future(demo_loop(user_session, get_time, trade_id, 1))
    asyncio.ensure_future(demo_loop(user_session, current_average_price, trade_id, 2))

    await asyncio.sleep(15)

    # Stop user session and close aiohttp session
    await user_session.stop()
    await session.close()
    print(f"Operational status: {user_session.operational_status}")


async def demo_loop(_session, _method, _trade_id, delay):
    for _ in range(10):
        await _method(_session, _trade_id)
        await asyncio.sleep(delay)


async def get_time(user_session: UserWSSession, _trade_id):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#check-server-time
    try:
        res = await user_session.handle_request(
                "time",
                _trade_id,
            )
        if res is None:
            print("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Check server time response: {res}")


async def current_average_price(user_session: UserWSSession, _trade_id):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#current-average-price
    try:
        params = {
            "symbol": "BNBBTC",
        }
        res = await user_session.handle_request(
            "avgPrice",
            _trade_id,
            params,
        )
        if res is None:
            print("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Current average price response: {res}")


async def account_information(user_session: UserWSSession, _trade_id):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#account-information-user_data
    try:
        res = await user_session.handle_request(
            "account.status",
            _trade_id,
            _api_key=True,
            _signed=True
        )
        if res is None:
            print("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Account information (USER_DATA) response: {res}")


if __name__ == '__main__':
    logger.info("INFO logging message from demo.main()")
    asyncio.run(main('Demo - Binance'))
