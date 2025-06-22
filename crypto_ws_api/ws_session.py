#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import gc
import sys
import time
import logging.handlers
from pathlib import Path
import ujson as json
from ujson import JSONDecodeError
import hmac
import hashlib
import base64
import string
import random
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from websockets.asyncio.client import connect
from websockets import ConnectionClosed

from enum import Enum
from crypto_ws_api import TIMEOUT, ID_LEN_LIMIT, DELAY, DEBUG_LOG

from exchanges_wrapper import LOG_PATH

sys.tracebacklimit = 0

ALPHABET = string.ascii_letters + string.digits
CONST_WS_START = "userDataStream.start"

def set_logger(name, log_file, file_level=logging.INFO, propagate=False):
    formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
    #
    fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=1000000, backupCount=10)
    fh.setFormatter(formatter)
    fh.setLevel(file_level)
    #
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    sh.setLevel(logging.INFO)
    #
    _logger = logging.getLogger(name)
    _logger.addHandler(fh)
    _logger.addHandler(sh)
    _logger.propagate = propagate

    return _logger

logger = set_logger(__name__, Path(LOG_PATH, 'ws_session.log'))


def generate_signature(exchange: str, secret: str, data: str) -> str:
    encoding = "utf-8"
    if exchange == 'binance':
        signature = load_pem_private_key(
            data=bytes(secret, encoding=encoding), password=None).sign(data.encode("ascii")
            )
    else:
        digest_func = hashlib.sha384 if exchange == 'bitfinex' else hashlib.sha256
        key = secret.encode(encoding=encoding)
        signature = hmac.new(
            bytes(key) if exchange == 'bybit' else key,
            data.encode(encoding=encoding),
            digest_func
        )
    if exchange in {"huobi", "okx"}:
        signature = signature.digest()

    if exchange in {"binance", "huobi", "okx"}:
        return base64.b64encode(signature).decode()
    else:
        return signature.hexdigest()

def compose_binance_ws_auth(_id: str, api_key: str, api_secret: str) -> dict:
    req = {"id": _id, "method": "session.logon"}
    params = {
        "apiKey": api_key,
        "timestamp": int(time.time() * 1000)
    }
    payload = '&'.join(f"{key}={value}" for key, value in sorted(params.items()))
    params["signature"] = generate_signature('binance', api_secret, payload)
    req["params"] = params
    return req

def compose_htx_ws_auth(endpoint, exchange, api_key, api_secret):
    _params = {
        "accessKey": api_key,
        "signatureMethod": "HmacSHA256",
        "signatureVersion": "2.1",
        "timestamp": str(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
    }
    signature_payload = (f"GET\n{urlparse(endpoint).hostname}\n{urlparse(endpoint).path}\n"
                         f"{urlencode(_params)}")
    signature = generate_signature(exchange, api_secret, signature_payload)
    _params["authType"] = "api"
    _params["signature"] = signature
    return {
        "action": "req",
        "ch": "auth",
        "params": _params
    }

# https://binance-docs.github.io/apidocs/websocket_api/en/#rate-limits
class RateLimitInterval(Enum):
    SECOND = 1
    MINUTE = 60
    HOUR = 3600
    DAY = 86400


class UserWSS:
    __slots__ = (
        "init",
        "exchange",
        "endpoint",
        "_api_key",
        "_api_secret",
        "_passphrase",
        "_ws",
        "_retry_after",
        "ws_id",
        "operational_status",
        "order_handling",
        "request_limit_reached",
        "in_event",
        "_response_pool",
        "tasks",
        "ping",
        "logger"
    )

    def __init__(self, ws_id, exchange, endpoint, api_key, api_secret, passphrase=None, trade_id=None):
        self.init = True
        self.exchange = exchange
        self.endpoint = endpoint
        #
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._ws = None
        self._response_pool = {}
        self._retry_after = int(time.time() * 1000) - 1
        self.ws_id = ws_id
        self.operational_status = None
        self.order_handling = False
        self.request_limit_reached = False
        self.in_event = asyncio.Event()
        self.tasks = set()
        self.ping = 0

        if self.exchange == DEBUG_LOG:
            if trade_id in logging.root.manager.loggerDict:
                logger.info(f"Logger {trade_id} already exists")
                self.logger = logging.root.manager.loggerDict[trade_id]
            else:
                self.logger = set_logger(trade_id, Path(LOG_PATH, f"ws_{trade_id}.log"), logging.DEBUG)
        else:
            self.logger = logger

    def tasks_manage(self, coro, name=None):
        _t = asyncio.create_task(coro, name=name)
        self.tasks.add(_t)
        _t.add_done_callback(self.tasks.discard)

    async def _ws_listener(self):
        self.tasks_manage(self.ws_login())
        async for msg in self._ws:
            # logger.info(f"_ws_listener: ws_id: {self.ws_id} msg: {msg}")
            if isinstance(msg, str):
                try:
                    _msg = json.loads(msg)
                except JSONDecodeError:
                    logger.warning(f"UserWSS: {self.ws_id}: {msg}")
                else:
                    res = await self._handle_msg(_msg)
                    # logger.info(f"_ws_listener: res: {self.ws_id}: {res}")
                    if res != 'pass':
                        if res is None:
                            self._response_pool[f"NoneResponse{self.ws_id}"] = None
                        elif self.exchange == 'binance':
                            self._response_pool[res.get('id')] = res.get('result')
                        elif self.exchange in {'okx', 'bitfinex'}:
                            self._response_pool[res.get('id') or self.ws_id] = res.get('data') or res
                        elif self.exchange == 'huobi':
                            self._response_pool[res.get('cid') or self.ws_id] = res.get('data')
                        self.in_event.set()
                        # logger.info(f"_ws_listener: _response_pool: {self._response_pool}")
                    await asyncio.sleep(0)
            else:
                logger.warning(f"UserWSS: {self.ws_id}: {msg}")
                await self.stop()

    async def start_wss(self):
        try:
            async for self._ws in connect(
                    self.endpoint,
                    logger=self.logger,
                    ping_interval=None if self.exchange in ('binance', 'huobi') else 20
            ):
                try:
                    await self._ws_listener()
                except ConnectionClosed as ex:
                    if ex.rcvd and ex.rcvd.code == 4000:
                        logger.info(f"WSS closed for {self.ws_id}")
                        break
                    else:
                        self.operational_status = False
                        [task.cancel() for task in self.tasks if not task.done()]
                        self.tasks.clear()
                        logger.warning(f"Restart UserWSS for {self.ws_id}")
                        continue
                except Exception as ex:
                    logger.error(f"UserWSS start other exception: {ex}")
        except asyncio.CancelledError:
            await self.stop()
            raise

    async def ws_login(self):
        res = await self.request(CONST_WS_START)
        if res is None:
            logger.warning(f"UserWSS: Not 'logged in' for {self.ws_id}")
            await self.stop()
        else:
            if self.exchange == 'huobi':
                self.tasks_manage(self.htx_keepalive(), f"htx_keepalive-{self.ws_id}")

            self.operational_status = True
            self.order_handling = True
            self.tasks_manage(self._keepalive(), f"keepalive-{self.ws_id}")
            logger.info(f"UserWSS: 'logged in' for {self.ws_id}")

    async def request(self, method, _params=None, _signed=False):
        """
        Construct and handling request/response to WS API endpoint, use a description of the methods on
        https://developers.binance.com/docs/binance-spot-api-docs/websocket-api
        :return: result: {} or None if temporary Out-of-Service state
        """
        if self.request_limit_reached:
            logger.warning(f"UserWSS {self.ws_id}: request limit reached, try later")
            return None
        if method != CONST_WS_START and not self.operational_status:
            logger.warning("UserWSS temporary in Out-of-Service state")
            return None
        if method in ('order.place', 'order.cancelReplace', 'order', 'create-order') and not self.order_handling:
            logger.warning("UserWSS: exceeded order placement limit, try later")
            return None
        params = _params.copy() if _params else None
        r_id = f"{self.exchange}{method}{''.join(random.choices(ALPHABET, k=8))}"
        if self.exchange in ("okx", "bitfinex", "huobi") and method == CONST_WS_START:
            _id = self.ws_id
        else:
            _id = ''.join(e for e in r_id if e.isalnum())[-ID_LEN_LIMIT.get(self.exchange, 64):]
        await self._ws.send(
            json.dumps(self.compose_request(_id, method, params, _signed))
        )
        await asyncio.sleep(0)
        try:
            res = await asyncio.wait_for(self._response_distributor(_id), timeout=TIMEOUT)
        except asyncio.exceptions.TimeoutError:
            logger.warning(f"UserWSS: get response timeout error: {self.ws_id}")
            await self.stop()
            return None
        else:
            return res

    async def _response_distributor(self, _id):
        while self.operational_status is not None:
            await self.in_event.wait()
            self.in_event.clear()
            if _id in self._response_pool:
                return self._response_pool.pop(_id)
            elif f"NoneResponse{self.ws_id}" in self._response_pool:
                return self._response_pool.pop(f"NoneResponse{self.ws_id}", None)
        return None

    def compose_request(self, _id, method, params, signed):
        if self.exchange == "binance":
            return self._compose_binance_request(_id, method, params, signed)
        elif self.exchange == "okx":
            return self._compose_okx_request(_id, method, params)
        elif self.exchange == "bitfinex":
            return self._compose_bitfinex_request(_id, method, params)
        elif self.exchange == "huobi":
            return self._compose_htx_request(_id, method, params)
        else:
            raise ValueError(f"Unsupported exchange: {self.exchange}")

    def _compose_htx_request(self, _id, method, params):
        if method == CONST_WS_START:
            return compose_htx_ws_auth(self.endpoint, self.exchange, self._api_key, self._api_secret)
        else:
            return {"cid": _id, "ch": method, "params": params}

    def _compose_binance_request(self, _id, method, params, signed):
        if method == CONST_WS_START:
            return compose_binance_ws_auth(_id, self._api_key, self._api_secret)
        else:
            req = {"id": _id, "method": method}
            params = params or {}
            if signed:
                params["timestamp"] = int(time.time() * 1000)
            if params:
                req["params"] = params
            return req

    def _compose_okx_request(self, _id, method, params):
        if method == CONST_WS_START:
            ts = int(time.time())
            signature_payload = f"{ts}GET/users/self/verify"
            signature = generate_signature(self.exchange, self._api_secret, signature_payload)
            return {
                "op": 'login',
                "args": [
                    {"apiKey": self._api_key, "passphrase": self._passphrase, "timestamp": ts, "sign": signature}
                ]
            }
        else:
            return {"id": _id, "op": method, "args": params if isinstance(params, list) else [params]}

    def _compose_bitfinex_request(self, _id, method, params):
        if method == CONST_WS_START:
            ts = int(time.time() * 1000)
            data = f"AUTH{ts}"
            return {
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
            return [0, method, _id, params]

    async def _keepalive(self, interval=10):
        while self.operational_status is not None:
            if self.request_limit_reached and (int(time.time() * 1000) - self._retry_after >= 0):
                self.request_limit_reached = False
                logger.info(f"UserWSS: request limit reached restored for {self.ws_id}")
            if not self.order_handling and (int(time.time() * 1000) - self._retry_after >= 0):
                self.order_handling = True
                logger.info(f"UserWSS order handling status restored for {self.ws_id}")
            await asyncio.sleep(interval)

    async def htx_keepalive(self, interval=60):
        await asyncio.sleep(interval * 10)
        while True:
            await asyncio.sleep(interval)
            if self.ping:
                break
            else:
                self.ping = 1
        logger.warning("From HTX server PING timeout exceeded")
        await self.stop()

    async def stop(self):
        """
        Stop data stream
        """
        self.operational_status = None  # Not restart and break all loops
        self.order_handling = False
        self.init = True
        [task.cancel() for task in self.tasks if not task.done()]
        self.tasks.clear()
        if self._ws:
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
                self.okx_error_handle(msg)
                msg = None
            return msg
        elif self.exchange == 'bitfinex':
            return await self.bitfinex_error_handle(msg)
        elif self.exchange == 'huobi':
            if msg.get('action') == 'ping':
                pong = {
                    "action": "pong",
                    "data": {
                        "ts": msg.get('data').get('ts')
                    }
                }
                self.ping = 0
                await self._ws.send(json.dumps(pong))
                return 'pass'

            if msg.get('code') == 200 or msg.get('status') == 'ok':
                return msg

            self.htx_error_handle(msg)
        return None

    def htx_error_handle(self, msg):
        if msg.get('code') == 500:
            logger.warning(f"An issue occurred on exchange's side: {msg}")
        elif msg.get('code') in {429, 4000}:
            self._retry_after = int((time.time() + TIMEOUT) * 1000)
            self.request_limit_reached = True
            logger.warning(f"HTX WSS exceed limit: {msg}")
        else:
            logger.warning(f"Malformed request: status: {msg}")

    # region BitfinexErrorHandle
    async def bitfinex_error_handle(self, msg):
        if isinstance(msg, dict):
            return await self._handle_dict_message(msg)
        elif isinstance(msg, list) and msg[1] == 'n' and msg[2][1] in ('on-req', 'oc-req', 'oc_multi-req'):
            return self._transform_list_message(msg)
        else:
            return 'pass'

    async def _handle_dict_message(self, msg):
        event = msg.get('event')
        if event == 'info':
            return await self._handle_info_event(msg)
        elif event == 'auth':
            return msg if msg.get('status') == "OK" else None
        elif msg.get('code'):
            return self._handle_error_code(msg)
        return 'pass'

    async def _handle_info_event(self, msg):
        if not msg.get('platform', {}).get('status'):
            logger.warning(f"UserWSS Bitfinex platform in maintenance mode: {msg}")
            await self.stop()
        elif msg.get('version') != 2:
            logger.critical('Bitfinex WSS platform: version change detected')
        return 'pass'

    def _handle_error_code(self, msg):
        code = msg.get('code')
        if code == 10305:
            logger.warning('UserWSS Bitfinex: Reached limit of open channels')
            self._retry_after = int((time.time() + TIMEOUT) * 1000)
            self.request_limit_reached = True
        else:
            logger.warning(f"Malformed request for {self.ws_id}: {msg}")

    @staticmethod
    def _transform_list_message(msg):
        return {
            "id": msg[2][2],
            "data": [
                msg[2][0],
                msg[2][1],
                None,
                None,
                [msg[2][4]] if msg[2][1] == 'on-req' else msg[2][4],
                None,
                msg[2][6],
                msg[2][7]
            ]
        }
    # endregion

    def okx_error_handle(self, msg):
        if msg.get('code') == '1':
            logger.warning(f"OKX User WSS operation failed: {msg}")
        elif msg.get('code') == '63999':
            logger.warning(f"An issue occurred on exchange's side: {msg}")
        elif msg.get('code') == '60014':
            self._retry_after = int((time.time() + TIMEOUT) * 1000)
            self.request_limit_reached = True
        else:
            logger.warning(f"Malformed request: status: {msg}")

    async def binance_error_handle(self, msg):
        error_msg = msg.get('error')
        logger.error(f"Malformed request: status: {error_msg}")
        if msg.get('status') in (401, 403):
            await self.stop()
        if msg.get('status') in (418, 429):
            self._retry_after = error_msg.get('data', {}).get('retryAfter', int((time.time() + TIMEOUT) * 1000))
            self.request_limit_reached = True

    def _handle_rate_limits(self, rate_limits: list):
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
        "tasks_wss",
    )

    def __init__(self, exchange, endpoint, api_key, api_secret, passphrase=None):
        if exchange not in ('binance', 'okx', 'bitfinex', 'huobi'):
            raise UserWarning(f"UserWSSession: exchange {exchange} not serviced")
        self.exchange = exchange
        self.endpoint = endpoint
        #
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self.user_wss = {}
        self.tasks_wss = set()

    async def handle_request(
        self,
        trade_id: str,
        method: str,
        _params=None,
        _signed=False,
    ):

        ws_id = f"{self.exchange}-{trade_id}"
        if self.exchange in ('binance', 'vertex'):
            ws_id = f"{ws_id}{'_ST' if _signed else '_SF'}"
        else:
            ws_id = f"{ws_id}-{method}"

        if ws_id in self.user_wss:
            user_wss = self.user_wss[ws_id]
        else:
            user_wss = UserWSS(
                    ws_id,
                    self.exchange,
                    self.endpoint,
                    self._api_key,
                    self._api_secret,
                    self._passphrase,
                    trade_id
                )
            self.user_wss[ws_id] = user_wss

        if user_wss.init:
            user_wss.init = False
            user_wss.operational_status = False
            _t = asyncio.create_task(user_wss.start_wss())
            self.tasks_wss.add(_t)
            _t.add_done_callback(self.tasks_wss.discard)

        duration = 0
        while not (user_wss.operational_status and user_wss.order_handling):
            await asyncio.sleep(DELAY)
            if duration > TIMEOUT:
                logger.warning(f"{trade_id}: Register timeout for method '{method}'")
                return None
            duration += DELAY

        try:
            return await user_wss.request(method=method, _params=_params, _signed=_signed)
        except KeyboardInterrupt:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logger.error(f"crypto_ws_api.ws_session.handle_request(): {ex}")
        logger.warning(f"{trade_id}: {method}: None response")
        return None

    async def stop(self):
        user_wss_copy = dict(self.user_wss)
        for ws in user_wss_copy.values():
            await ws.stop()
        self.user_wss.clear()
        [task.cancel() for task in self.tasks_wss if not task.done()]
        self.tasks_wss.clear()
