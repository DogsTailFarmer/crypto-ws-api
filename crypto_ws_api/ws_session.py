#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import time
import aiohttp
import logging
import json

from exchanges_wrapper.c_structures import generate_signature
from exchanges_wrapper.definitions import RateLimitInterval
from exchanges_wrapper.errors import ExchangeError, WAFLimitViolated, IPAddressBanned, RateLimitReached, HTTPError

from crypto_ws_api import TIMEOUT, ID_LEN_LIMIT


logger = logging.getLogger(__name__)


class UserWSS:

    '''
    __slots__ = (
        "_api_key",
        "_api_secret",
        "_passphrase",
        "_session",
        "_endpoint",
        "_ws",
        "_listen_key",
        "_try_count",
        "_retry_after",
        "_session_tasks",
        "_queue",
        "exchange",
        "trade_id",
        "operational_status",
        "order_handling",
        "in_recovery",
    )
    '''

    def __init__(self, session, method, ws_id, exchange, endpoint, api_key, api_secret, passphrase=None):
        self.init = None
        self.session = session
        self.method = method
        self.exchange = exchange
        self.endpoint = endpoint
        #
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._ws = None
        self._listen_key = None
        self._queue = asyncio.Queue()
        #
        self._retry_after = int(time.time() * 1000) - 1
        self.ws_id = ws_id
        self.operational_status = None
        self.order_handling = False
        self.request_limit_reached = False

    async def get_ws(self):
        logger.info(f"get_ws: START: {self.ws_id}")
        self.init = True
        _heartbeat = None
        _receive_timeout = None
        if self.exchange == 'binance':
            _heartbeat = 500
        elif self.exchange == 'bitfinex':
            _receive_timeout = 30
        elif self.exchange == 'okx':
            _heartbeat = 25
        while self.operational_status is not None:
            while self.init:
                try:
                    self._ws = await self.session.ws_connect(
                        self.endpoint,
                        heartbeat=_heartbeat,
                        receive_timeout=_receive_timeout
                    )
                except aiohttp.ClientError as ex:
                    logger.warning(f"UserWSS: {ex}")
                    await asyncio.sleep(TIMEOUT)
                else:
                    self.operational_status = True
                    self.init = False
                    logger.info(f"UserWSS: started for: {self.ws_id}")
            while self.operational_status:
                msg = await self._ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # logger.debug(f"get_ws: msg: {msg}")
                    await self._queue.put(json.loads(msg.data))
                else:
                    logger.error(f"UserWSS: {self.ws_id}: {msg}")
                    await self._ws.close()
                    self.operational_status = None
                    self.init = None
            logger.warning(f"UserWSSession: WSS receive loop stopped: {self.ws_id}")
        logger.warning(f"get_ws: stopped: {self.ws_id}")

    async def ws_login(self):
        res = await self.request('userDataStream.start', _api_key=True)
        if self.exchange == 'binance' and res:
            self._listen_key = res.get('listenKey')
            asyncio.ensure_future(self.heartbeat())
        else:
            self._listen_key = f"{int(time.time() * 1000)}{self.ws_id}"
        self.order_handling = True
        asyncio.ensure_future(self._keepalive())
        logger.info(f"UserWSSession: logged in for {self.ws_id}")

    async def request(self, _method=None, _params=None, _api_key=False, _signed=False):
        """
        Construct and handling request/response to WS API endpoint, use a description of the methods on
        https://developers.binance.com/docs/binance-trading-api/websocket_api#request-format
        :return: result: {} or None if temporary Out-of-Service state
        """
        method = _method or self.method
        if self.request_limit_reached:
            logger.warning(f"UserWSSession {self.ws_id}: request limit reached, try later")
            return None
        if method != 'userDataStream.start' and not self.operational_status:
            logger.warning("UserWSSession operational status is %s", self.operational_status)
            return None
        if method in ('order.place', 'order.cancelReplace', 'order') and not self.order_handling:
            logger.warning("UserWSSession: exceeded order placement limit, try later")
            return None

        params = _params.copy() if _params else None
        if self.exchange == 'bitfinex':
            _id = None
        else:
            _id = ''.join(e for e in self.ws_id if e.isalnum())[-ID_LEN_LIMIT[self.exchange]:]
        await self._ws.send_json(
            self.compose_request(_id, _api_key, method, params, _signed)
        )
        try:
            res = await asyncio.wait_for(self._queue.get(), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"UserWSS get() timeout error: {self.ws_id}")
            await self._ws.close()
            self.operational_status = None
            self.init = None
            return None
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        else:
            return self._handle_msg_error(res)

    def compose_request(self, _id, api_key, method, params, signed):
        req = None
        if self.exchange == "binance":
            req = {"id": _id, "method": method}
            if (api_key or signed) and not params:
                params = {}
            if api_key:
                params["apiKey"] = self._api_key
            if signed:
                params["timestamp"] = int(time.time() * 1000)
                payload = '&'.join(f"{key}={value}" for key, value in dict(sorted(params.items())).items())
                params["signature"] = generate_signature('binance_ws', self._api_secret, payload)
            if params:
                req["params"] = params
        elif self.exchange == "okx":
            if method == "userDataStream.start":
                # https://www.okx.com/docs-v5/en/?python#overview-websocket-connect
                ts = int(time.time())
                signature_payload = f"{ts}GET/users/self/verify"
                signature = generate_signature(self.exchange, self._api_secret, signature_payload)
                # Login on account
                req = {"op": 'login',
                       "args": [{"apiKey": self._api_key,
                                 "passphrase": self._passphrase,
                                 "timestamp": ts,
                                 "sign": signature}
                                ]
                       }
            elif method == "ping":
                req = "ping"
            else:
                req = {"id": _id, "op": method, "args": params if isinstance(params, list) else [params]}
        elif self.exchange == 'bitfinex':
            ts = int(time.time() * 1000)
            data = f"AUTH{ts}"
            req = {
                'event': "auth",
                'apiKey': self._api_key,
                'authSig': generate_signature(self.exchange, self._api_secret, data),
                'authPayload': data,
                'authNonce': ts,
                'filter': []
            }
        return req

    async def _keepalive(self, interval=10):
        while self.operational_status is not None:
            if self.request_limit_reached and (int(time.time() * 1000) - self._retry_after >= 0):
                self.request_limit_reached = False
                logger.info(f"UserWSSession: request limit reached restored for {self.ws_id}")
            if not self.order_handling and (int(time.time() * 1000) - self._retry_after >= 0):
                self.order_handling = True
                logger.info(f"UserWSSession order handling status restored for {self.ws_id}")
            await asyncio.sleep(interval)

    async def heartbeat(self, interval=60 * 30):
        params = {
            "listenKey": self._listen_key,
        }
        while self.operational_status is not None:
            await self.request(
                "userDataStream.ping",
                params,
                _api_key=True,
            )
            await asyncio.sleep(interval)

    async def stop(self):
        """
        Stop data stream
        """
        logger.info("STOP User WSS for %s", self.ws_id)
        self.operational_status = None  # Not restart and break all loops
        self.order_handling = False
        self._ws.close()
        self._queue = None

    def _handle_msg_error(self, msg):
        if self.exchange == 'binance':
            if msg.get('status') != 200:
                self.binance_error_handle(msg)
                return None
            return msg.get('result')
        elif self.exchange == 'okx':
            if msg.get('code') != '0' and (
                msg.get('code') != '60012' or 'ping' not in msg.get('msg')
            ):
                if msg.get('code') == '63999':
                    raise ExchangeError(f"An issue occurred on exchange's side: {msg}")
                if msg.get('code') == '60014':
                    self.operational_status = False
                    raise RateLimitReached(RateLimitReached.message)
                raise HTTPError(f"Malformed request: status: {msg}")
            return msg.get('data', [])

    def binance_error_handle(self, msg):
        error_msg = msg.get('error')
        if msg.get('status') >= 500:
            logger.error(f"An issue occurred on exchange's side: {error_msg}")
        if msg.get('status') == 403:
            self.operational_status = False
            logger.error(error_msg)
        self._retry_after = error_msg.get('data', {}).get('retryAfter', int((time.time() + 10) * 1000))
        if msg.get('status') == 418:
            self.operational_status = False
            raise IPAddressBanned(IPAddressBanned.message)
        if msg.get('status') == 429:
            self.operational_status = False
            raise RateLimitReached(RateLimitReached.message)
        logger.error(f"Malformed request: status: {error_msg}")

    def _handle_rate_limits(self, rate_limits: []):
        def retry_after():
            return (int(time.time() / interval) + 1) * interval * 1000

        for rl in rate_limits:
            if rl.get('limit') - rl.get('count') <= 0:
                interval = rl.get('intervalNum') * RateLimitInterval[rl.get('interval')].value
                self._retry_after = max(self._retry_after, retry_after())
                if rl.get('rateLimitType') == 'REQUEST_WEIGHT':
                    self.request_limit_reached = True
                elif rl.get('rateLimitType') == 'ORDERS':
                    self.order_handling = False


class UserWSSession:
    '''
    __slots__ = (
        "_api_key",
        "_api_secret",
        "_passphrase",
        "_session",
        "_endpoint",
        "_ws",
        "_listen_key",
        "_try_count",
        "_retry_after",
        "_session_tasks",
        "_queue",
        "exchange",
        "trade_id",
        "operational_status",
        "order_handling",
        "in_recovery",
    )
    '''
    def __init__(self, session, exchange, endpoint, api_key, api_secret, passphrase=None):
        if exchange not in ('binance', 'okx', 'bitfinex'):
            raise UserWarning(f"UserWSSession: exchange {exchange} not serviced")
        self.session = session
        self.exchange = exchange
        self.endpoint = endpoint
        #
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self.user_wss = {}

    async def handle_request(
            self,
            trade_id: str,
            method: str,
            _params=None,
            _api_key=False,
            _signed=False,
    ):
        ws_id = f"{self.exchange}-{trade_id}-{method}"
        user_wss = self.user_wss.setdefault(
            ws_id,
            UserWSS(
                self.session,
                method,
                ws_id,
                self.exchange,
                self.endpoint,
                self._api_key,
                self._api_secret,
                self._passphrase
            )
        )
        _init = None
        if user_wss.init is None:
            _init = True
            user_wss.operational_status = False
            asyncio.ensure_future(user_wss.get_ws())
        else:
            while not (user_wss.operational_status and user_wss.order_handling):
                await asyncio.sleep(1)
        while user_wss.init is None or user_wss.init:
            await asyncio.sleep(1)
        if _init:
            await user_wss.ws_login()
        try:
            res = await user_wss.request(_params=_params, _api_key=_api_key, _signed=_signed)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        else:
            return res

    async def stop(self):
        for ws in self.user_wss.values():
            await ws.stop()
