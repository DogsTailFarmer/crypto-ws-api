#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import gc
import sys
import time
import logging
import json
import hmac
import hashlib
import base64
import string
import random
import websockets.client

from websockets import ConnectionClosed

from enum import Enum
from crypto_ws_api import TIMEOUT, ID_LEN_LIMIT, DELAY

logger_ws = logger = logging.getLogger(__name__)
logger_ws.level = logging.INFO
sys.tracebacklimit = 0
ALPHABET = string.ascii_letters + string.digits


def generate_signature(exchange, api_secret, data):
    if exchange == 'bitfinex':
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha384).hexdigest()
    elif exchange in ('huobi', 'okx'):
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
        sig = base64.b64encode(sig).decode()
    elif exchange == 'binance_ws':
        sig = hmac.new(api_secret.encode("ascii"), data.encode("ascii"), hashlib.sha256).hexdigest()
    elif exchange == 'bybit':
        sig = hmac.new(bytes(api_secret.encode("utf-8")), data.encode("utf-8"), hashlib.sha256).hexdigest()
    else:
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig


# https://binance-docs.github.io/apidocs/websocket_api/en/#rate-limits
class RateLimitInterval(Enum):
    SECOND = 1
    MINUTE = 60
    HOUR = 3600
    DAY = 86400


class UserWSS:
    __slots__ = (
        "init",
        "method",
        "exchange",
        "endpoint",
        "_api_key",
        "_api_secret",
        "_passphrase",
        "_ws",
        "_listen_key",
        "_retry_after",
        "ws_id",
        "operational_status",
        "order_handling",
        "request_limit_reached",
        "in_event",
        "_response_pool",
        "tasks_list",
    )

    def __init__(self, method, ws_id, exchange, endpoint, api_key, api_secret, passphrase=None):
        self.init = True
        self.method = method
        self.exchange = exchange
        self.endpoint = endpoint
        #
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._ws = None
        self._listen_key = None
        self._response_pool = {}
        self._retry_after = int(time.time() * 1000) - 1
        self.ws_id = ws_id
        self.operational_status = None
        self.order_handling = False
        self.request_limit_reached = False
        self.in_event = asyncio.Event()
        self.tasks_list = []

    async def _ws_listener(self):
        asyncio.ensure_future(self.ws_login())
        async for msg in self._ws:
            # logger.info(f"_ws_listener: msg: {self.ws_id}: {msg}")
            if isinstance(msg, str):
                res = await self._handle_msg(json.loads(msg))
                # logger.info(f"_ws_listener: res: {self.ws_id}: {res}")
                if res != 'pass':
                    if res is None:
                        self._response_pool[f"NoneResponse{self.ws_id}"] = None
                    elif self.exchange == 'binance':
                        self._response_pool[res.get('id')] = res.get('result')
                    elif self.exchange in ['okx', 'bitfinex']:
                        self._response_pool[res.get('id') or self.ws_id] = res.get('data') or res
                    self.in_event.set()
                    await asyncio.sleep(0)
            else:
                logger.warning(f"UserWSS: {self.ws_id}: {msg}")
                await self.stop()

    async def start_wss(self):
        async for self._ws in websockets.client.connect(self.endpoint, logger=logger_ws):
            try:
                await self._ws_listener()
            except ConnectionClosed as ex:
                if ex.code == 4000:
                    logger.info(f"WSS closed for {self.ws_id}")
                    break
                else:
                    self.operational_status = False
                    [task.cancel() for task in self.tasks_list if not task.done()]
                    self.tasks_list.clear()
                    logger.warning(f"Restart WSS for {self.ws_id}")
                    continue
            except Exception as ex:
                logger.error(f"WSS start_wss() other exception: {ex}")

    async def ws_login(self):
        res = await self.request('userDataStream.start', _api_key=True)
        if res is None:
            logger.warning(f"UserWSS: Not 'logged in' for {self.ws_id}")
            raise ConnectionClosed
        else:
            if self.exchange == 'binance':
                self._listen_key = res.get('listenKey')
                _t = asyncio.ensure_future(self.heartbeat())
                _t.set_name(f"heartbeat-{self.ws_id}")
                self.tasks_list.append(_t)
            else:
                self._listen_key = f"{int(time.time() * 1000)}{self.ws_id}"
            self.operational_status = True
            self.order_handling = True
            _t = asyncio.ensure_future(self._keepalive())
            _t.set_name(f"keepalive-{self.ws_id}")
            self.tasks_list.append(_t)
            logger.info(f"UserWSS: 'logged in' for {self.ws_id}")

    async def request(self, _method=None, _params=None, _api_key=False, _signed=False):
        """
        Construct and handling request/response to WS API endpoint, use a description of the methods on
        https://developers.binance.com/docs/binance-trading-api/websocket_api#request-format
        :return: result: {} or None if temporary Out-of-Service state
        """
        method = _method or self.method
        if self.request_limit_reached:
            logger.warning(f"UserWSS {self.ws_id}: request limit reached, try later")
            return None
        if method != 'userDataStream.start' and not self.operational_status:
            logger.warning("UserWSS temporary in Out-of-Service state")
            return None
        if method in ('order.place', 'order.cancelReplace', 'order') and not self.order_handling:
            logger.warning("UserWSS: exceeded order placement limit, try later")
            return None
        params = _params.copy() if _params else None
        r_id = f"{self.exchange}{method}{''.join(random.choices(ALPHABET, k=8))}"
        if self.exchange in ("okx", "bitfinex") and method == "userDataStream.start":
            _id = self.ws_id
        else:
            _id = ''.join(e for e in r_id if e.isalnum())[-ID_LEN_LIMIT[self.exchange]:]
        await self._ws.send(
            json.dumps(self.compose_request(_id, _api_key, method, params, _signed))
        )
        try:
            res = await asyncio.wait_for(self._response_distributor(_id), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"UserWSS: get response timeout error: {self.ws_id}")
            await self.stop()
            return None
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        else:
            # logger.info(f"request: {self.ws_id}: {res}")
            return res

    async def _response_distributor(self, _id):
        while self.operational_status is not None:
            await self.in_event.wait()
            self.in_event.clear()
            if _id in self._response_pool:
                return self._response_pool.pop(_id)
            elif f"NoneResponse{self.ws_id}" in self._response_pool:
                return self._response_pool.pop(f"NoneResponse{self.ws_id}", None)

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
            else:
                req = {"id": _id, "op": method, "args": params if isinstance(params, list) else [params]}
        elif self.exchange == 'bitfinex':
            if method == "userDataStream.start":
                ts = int(time.time() * 1000)
                data = f"AUTH{ts}"
                req = {
                    'event': "auth",
                    'apiKey': self._api_key,
                    'authSig': generate_signature(self.exchange, self._api_secret, data),
                    'authPayload': data,
                    'authNonce': ts,
                    'filter': ['trading']
                }
            else:
                if method == 'on':
                    params.update({"meta": {"aff_code": "v_4az2nCP"}})
                req = [0, method, _id, params]
        return req

    async def _keepalive(self, interval=10):
        while self.operational_status is not None:
            if self.request_limit_reached and (int(time.time() * 1000) - self._retry_after >= 0):
                self.request_limit_reached = False
                logger.info(f"UserWSS: request limit reached restored for {self.ws_id}")
            if not self.order_handling and (int(time.time() * 1000) - self._retry_after >= 0):
                self.order_handling = True
                logger.info(f"UserWSS order handling status restored for {self.ws_id}")
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
        self.operational_status = None  # Not restart and break all loops
        self.order_handling = False
        self.init = True
        [task.cancel() for task in self.tasks_list if not task.done()]
        self.tasks_list.clear()
        if self._ws and not self._ws.closed:
            await self._ws.close(code=4000)
        gc.collect()
        logger.info(f"User WSS for {self.ws_id} stopped")

    async def _handle_msg(self, msg):
        if self.exchange == 'binance':
            self._handle_rate_limits(msg.pop('rateLimits', []))
            if msg.get('status') != 200:
                await self.binance_error_handle(msg)
                msg = None
            return msg
        elif self.exchange == 'okx':
            if msg.get('code') != '0':
                await self.okx_error_handle(msg)
                msg = None
            return msg
        elif self.exchange == 'bitfinex':
            return await self.bitfinex_error_handle(msg)

    async def bitfinex_error_handle(self, msg):
        if isinstance(msg, dict):
            if msg.get('event') == 'info' and not msg.get('platform', {}).get('status'):
                logger.warning(f"UserWSS Bitfinex platform in maintenance mode: {msg}")
                await self.stop()
            if msg.get('event') == 'auth' and msg.get('status') == "OK":
                return msg
            if msg.get('event') == 'info' and msg.get('version') != 2:
                logger.critical('Bitfinex WSS platform: version change detected')
            # sourcery skip: merge-nested-ifs
            if msg.get('code'):
                if msg.get('code') == 10305:
                    logger.warning('UserWSS Bitfinex: Reached limit of open channels')
                    self._retry_after = int((time.time() + TIMEOUT) * 1000)
                    self.request_limit_reached = True
                logger.warning(f"Malformed request for {self.ws_id}: {msg}")
                return None
            return 'pass'
        elif isinstance(msg, list) and msg[1] == 'n' and msg[2][1] in ('on-req', 'oc-req', 'oc_multi-req'):
            msg = {"id": msg[2][2],
                   "data": [msg[2][0],
                            msg[2][1],
                            None,
                            None,
                            [msg[2][4]] if msg[2][1] == 'on-req' else msg[2][4],
                            None,
                            msg[2][6],
                            msg[2][7]
                            ]
                   }
            return msg
        else:
            return 'pass'

    async def okx_error_handle(self, msg):
        if msg.get('code') == '1':
            logger.warning(f"Operation failed: {msg}")
        elif msg.get('code') == '63999':
            logger.warning(f"An issue occurred on exchange's side: {msg}")
        elif msg.get('code') == '60014':
            self._retry_after = int((time.time() + TIMEOUT) * 1000)
            self.request_limit_reached = True
        logger.warning(f"Malformed request: status: {msg}")

    async def binance_error_handle(self, msg):
        error_msg = msg.get('error')
        logger.error(f"Malformed request: status: {error_msg}")
        if msg.get('status') == 403:
            await self.stop()
        if msg.get('status') in (418, 429):
            self._retry_after = error_msg.get('data', {}).get('retryAfter', int((time.time() + TIMEOUT) * 1000))
            self.request_limit_reached = True

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
    __slots__ = (
        "exchange",
        "endpoint",
        "_api_key",
        "_api_secret",
        "_passphrase",
        "user_wss",
    )

    def __init__(self, exchange, endpoint, api_key, api_secret, passphrase=None):
        if exchange not in ('binance', 'okx', 'bitfinex'):
            raise UserWarning(f"UserWSSession: exchange {exchange} not serviced")
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
                method,
                ws_id,
                self.exchange,
                self.endpoint,
                self._api_key,
                self._api_secret,
                self._passphrase
            )
        )

        if user_wss.init:
            user_wss.init = False
            user_wss.operational_status = False
            asyncio.ensure_future(user_wss.start_wss())

        duration = 0
        while not (user_wss.operational_status and user_wss.order_handling):
            await asyncio.sleep(DELAY)
            if duration > TIMEOUT:
                return None
            duration += DELAY

        try:
            return await user_wss.request(_params=_params, _api_key=_api_key, _signed=_signed)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logger.error(f"crypto_ws_api.ws_session.handle_request(): {ex}")
        return None

    async def stop(self):
        user_wss_copy = dict(self.user_wss)
        for ws in user_wss_copy.values():
            await ws.stop()
        self.user_wss.clear()
