#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import aiohttp
import asyncio
from crypto_ws_api.ws_session import get_credentials, UserWSSession


async def main(account_name):
    # Get credentials and create user session
    session = aiohttp.ClientSession()
    _, _, api_key, api_secret, ws_api_endpoint = get_credentials(account_name)

    user_session = UserWSSession(
        api_key,
        api_secret,
        session=session,
        endpoint=ws_api_endpoint
    )

    await user_session.start()
    print(f"Operational status: {user_session.operational_status}")

    # Demo method's calling
    await account_information(user_session)
    asyncio.ensure_future(demo_loop(user_session, get_time, 1))
    asyncio.ensure_future(demo_loop(user_session, current_average_price, 1))

    await asyncio.sleep(15)

    # Stop user session and close aiohttp session
    await user_session.stop()
    await session.close()
    print(f"Operational status: {user_session.operational_status}")


async def demo_loop(_session, _method, delay):
    for i in range(10):
        await _method(_session)
        await asyncio.sleep(delay)


async def get_time(user_session: UserWSSession):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#check-server-time
    try:
        res = {}
        ws_status = bool(user_session and user_session.operational_status)
        if ws_status:
            res = await user_session.handle_request(
                "time",
            )
        if not ws_status or res is None:
            pass  # Handling out of service state

    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Check server time response: {res}")


async def current_average_price(user_session: UserWSSession):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#current-average-price
    try:
        res = {}
        ws_status = bool(user_session and user_session.operational_status)
        if ws_status:
            params = {
                "symbol": "BNBBTC",
            }
            res = await user_session.handle_request(
                "avgPrice",
                params,
            )
        if not ws_status or res is None:
            pass  # Handling out of service state

    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Current average price response: {res}")


async def account_information(user_session: UserWSSession):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#account-information-user_data
    try:
        res = {}
        ws_status = bool(user_session and user_session.operational_status)
        if ws_status:
            res = await user_session.handle_request(
                "account.status",
                api_key=True,
                signed=True
            )
        if not ws_status or res is None:
            pass  # Handling out of service state

    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Account information (USER_DATA) response: {res}")


if __name__ == '__main__':
    asyncio.run(main('Demo - Binance'))
