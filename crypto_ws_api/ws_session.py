#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import random
import time
import aiohttp
import shortuuid
import toml
import logging

from exchanges_wrapper.c_structures import generate_signature
from exchanges_wrapper.definitions import RateLimitInterval
from exchanges_wrapper.errors import ExchangeError, WAFLimitViolated, IPAddressBanned, RateLimitReached, HTTPError

from crypto_ws_api import CONFIG_FILE, TIMEOUT, ID_LEN_LIMIT


logger = logging.getLogger(__name__)


class UserWSSession:
    __slots__ = (
        "_api_key",
        "_api_secret",
        "_passphrase",
        "_session",
        "_endpoint",
        "_web_socket",
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

    def __init__(self, exchange, api_key, api_secret, endpoint, passphrase=None, session: aiohttp.ClientSession = None):
        if exchange not in ('binance', 'okx', 'bitfinex'):
            raise UserWarning(f"UserWSSession: exchange {exchange} not serviced")
        if None in {api_key, api_secret, endpoint} or (exchange == 'okx' and passphrase is None):
            raise UserWarning("UserWSSession: all account parameters must be set")

        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._session = session or aiohttp.ClientSession()
        self._endpoint = endpoint
        self._web_socket = None
        self._listen_key = None
        self._try_count = 0
        self._retry_after = int(time.time() * 1000) - 1
        self._session_tasks = []
        self._queue = {}
        #
        self.exchange = exchange
        self.trade_id = None
        self.operational_status = False
        self.order_handling = False
        self.in_recovery = None

    async def start(self, trade_id=shortuuid.uuid()):
        self.trade_id = self.trade_id or trade_id
        heartbeat = None
        try:
            if self.exchange == 'bitfinex':
                self._web_socket = await self._session.ws_connect(self._endpoint, receive_timeout=30)
            else:
                if self.exchange == 'binance':
                    heartbeat = 500
                elif self.exchange == 'okx':
                    heartbeat = 25
                self._web_socket = await self._session.ws_connect(self._endpoint, heartbeat=heartbeat)
        except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectionError, asyncio.TimeoutError) as ex:
            self.in_recovery = None
            await self._ws_error(ex)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logger.error("UserWSSession: start() other exception: %s", ex)
        else:
            self._session_tasks.append(asyncio.ensure_future(self._receive_msg()))
            self.operational_status = True
            self.order_handling = True
            res = await self.handle_request('userDataStream.start', api_key=True)
            if self.exchange == 'binance' and res:
                self._listen_key = res.get('listenKey')
                self._session_tasks.append(asyncio.ensure_future(self._heartbeat()))
            else:
                self._listen_key = f"{self.trade_id}{int(time.time() * 1000)}"
            self.in_recovery = None
            self._try_count = 0
            self._session_tasks.append(asyncio.ensure_future(self._keepalive()))
            logger.info("UserWSSession started for %s", self.trade_id)

    async def _ws_error(self, ex):
        if self.operational_status is not None and self.in_recovery is None:
            self.in_recovery = True
            self._try_count += 1
            delay = random.randint(1, 5) * self._try_count
            logger.error(f"UserWSSession restart: delay: {delay}s, {ex}")
            await asyncio.sleep(delay)
            asyncio.ensure_future(self.start())

    async def handle_request(self, method: str, _params=None, api_key=False, signed=False):
        """
        Construct and handling request/response to WS API endpoint, use a description of the methods on
        https://developers.binance.com/docs/binance-trading-api/websocket_api#request-format
        :param method: 'method'
        :param _params: 'params'
        :param api_key: True if API key must be sent
        :param signed: True if signature must be sent
        :return: result: {} or None if temporary Out-of-Service state
        """
        if not self.operational_status:
            logger.warning("UserWSSession operational status is %s", self.operational_status)
            return None
        elif method in ('order.place', 'order.cancelReplace', 'order') and not self.order_handling:
            logger.warning("UserWSSession: exceeded order placement limit, try later")
            return None
        else:
            params = _params.copy() if _params else None
            if self.exchange == 'okx' and method in ('userDataStream.start', 'ping'):
                _id = f"{self.trade_id}{self.exchange}"
            else:
                _symbol = ''
                if self.exchange == 'binance' and params:
                    _symbol = params.get('symbol', '')
                elif self.exchange == 'okx' and params:
                    if isinstance(params, dict):
                        _symbol = params.get('instId', '')
                    elif isinstance(params, list):
                        _symbol = params[0].get('instId', '')
                _id = f"{self.trade_id}{method}{_symbol}"
            _id = ''.join(e for e in _id if e.isalnum())[-ID_LEN_LIMIT[self.exchange]:]
            queue = self._queue.setdefault(_id, asyncio.Queue())
            await self._send_request(
                self.compose_request(_id, api_key, method, params, signed)
            )
            try:
                res = await asyncio.wait_for(queue.get(), timeout=TIMEOUT)
            except asyncio.TimeoutError:
                ex = "UserWSSession timeout error"
                await self._ws_error(ex)
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
        listen_key = self._listen_key
        while self.operational_status is not None and self._listen_key == listen_key:
            await asyncio.sleep(interval)
            if ((not self.operational_status or not self.order_handling)
                    and int(time.time() * 1000) - self._retry_after >= 0):
                try:
                    await self.handle_request("ping")
                except asyncio.CancelledError:
                    pass  # Task cancellation should not be logged as an error
                except Exception as ex:
                    logger.warning("UserWSSession._keepalive: %s", ex)
                else:
                    if not self.operational_status:
                        self.operational_status = True
                        logger.info("UserWSSession operational status restored")
                    if not self.order_handling:
                        self.order_handling = True
                        logger.info("UserWSSession order limit restriction was cleared")
        logger.warning(f"UserWSSession: keepalive loop stopped for {self.trade_id}")

    async def _heartbeat(self, interval=60 * 30):
        params = {
            "listenKey": self._listen_key,
        }
        while self.operational_status is not None:
            await asyncio.sleep(interval)
            await self.handle_request("userDataStream.ping", params, api_key=True)

    async def stop(self):
        """
        Stop data stream
        """
        logger.info("STOP User WSS for %s", self.trade_id)
        self.operational_status = None  # Not restart and break all loops
        self.order_handling = False
        req = {
            "id": f"{self.trade_id}-stop",
            "method": "userDataStream.stop",
            "params": {
                "listenKey": self._listen_key,
                "apiKey": self._api_key
            }
        }
        await self._send_request(req)
        [_task.cancel() for _task in self._session_tasks]
        if self._web_socket:
            await self._web_socket.close()
        self._queue.clear()

    async def _send_request(self, req: {}):
        try:
            await self._web_socket.send_json(req)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except RuntimeError as ex:
            await self._ws_error(ex)
        except Exception as ex:
            logger.error("UserWSSession._send_request: %s", ex)

    async def _receive_msg(self):
        while self.operational_status is not None:
            msg = await self._web_socket.receive_json()

            print(f"_receive_msg: msg: {msg}")

            if self.exchange == 'binance':
                self._handle_rate_limits(msg.pop('rateLimits', []))

            queue = self._queue.get(msg.get('id') or f"{self.trade_id}{self.exchange}")
            if queue:
                await queue.put(msg)
            else:
                logger.warning("Can't get queue for transporting message: %s", msg)

    def _handle_msg_error(self, msg):
        if self.exchange == 'binance':
            if msg.get('status') != 200:
                error_msg = msg.get('error')
                if msg.get('status') >= 500:
                    raise ExchangeError(f"An issue occurred on exchange's side: {error_msg}")
                if msg.get('status') == 403:
                    self.operational_status = False
                    raise WAFLimitViolated(WAFLimitViolated.message)
                self._retry_after = error_msg.get('data', {}).get('retryAfter', int((time.time() + 10) * 1000))
                if msg.get('status') == 418:
                    self.operational_status = False
                    raise IPAddressBanned(IPAddressBanned.message)
                if msg.get('status') == 429:
                    self.operational_status = False
                    raise RateLimitReached(RateLimitReached.message)
                raise HTTPError(f"Malformed request: status: {error_msg}")
            return msg.get('result')
        elif self.exchange == 'okx':
            if msg.get('code') != '0' and not (msg.get('code') == '60012' and 'ping' in msg.get('msg')):
                if msg.get('code') == '63999':
                    raise ExchangeError(f"An issue occurred on exchange's side: {msg}")
                if msg.get('code') == '60014':
                    self.operational_status = False
                    raise RateLimitReached(RateLimitReached.message)
                raise HTTPError(f"Malformed request: status: {msg}")
            return msg.get('data', [])

    def _handle_rate_limits(self, rate_limits: []):
        def retry_after():
            return (int(time.time() / interval) + 1) * interval * 1000

        for rl in rate_limits:
            if rl.get('limit') - rl.get('count') <= 0:
                interval = rl.get('intervalNum') * RateLimitInterval[rl.get('interval')].value
                self._retry_after = max(self._retry_after, retry_after())
                if rl.get('rateLimitType') == 'REQUEST_WEIGHT':
                    self.operational_status = False
                elif rl.get('rateLimitType') == 'ORDERS':
                    self.order_handling = False


def get_credentials(_account_name: str) -> ():
    config = toml.load(str(CONFIG_FILE))
    accounts = config.get('accounts')
    for account in accounts:
        if account.get('name') == _account_name:
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
    raise UserWarning(f"Can't find account '{_account_name}' defined in {CONFIG_FILE}")
