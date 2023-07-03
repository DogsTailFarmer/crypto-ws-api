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

from crypto_ws_api import CONFIG_FILE, TIMEOUT


class UserWSSession:
    __slots__ = (
        "_api_key",
        "_api_secret",
        "_session",
        "_endpoint",
        "_web_socket",
        "_listen_key",
        "_try_count",
        "_retry_after",
        "_session_tasks",
        "_queue",
        "trade_id",
        "operational_status",
        "order_handling",
    )

    def __init__(
            self,
            api_key: str,
            api_secret: str,
            session: aiohttp.ClientSession,
            endpoint: str
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._session = session
        self._endpoint = endpoint
        self._web_socket = None
        self._listen_key = None
        self._try_count = 0
        self._retry_after = int(time.time() * 1000) - 1
        self._session_tasks = []
        self._queue = {}
        #
        self.trade_id = None
        self.operational_status = False
        self.order_handling = False

    async def start(self, trade_id=shortuuid.uuid()):
        self.trade_id = trade_id or self.trade_id
        try:
            self._web_socket = await self._session.ws_connect(url=f"{self._endpoint}", heartbeat=500)
        except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectionError, asyncio.TimeoutError) as ex:
            await self._ws_error(ex)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logging.error("UserWSSession: start() other exception: %s", ex)
        else:
            self._session_tasks.append(asyncio.ensure_future(self._receive_msg()))
            self.operational_status = True
            self.order_handling = True
            res = await self.handle_request('userDataStream.start', api_key=True)
            if res:
                self._try_count = 0
                self._listen_key = res.get('listenKey')
                self._session_tasks.append(asyncio.ensure_future(self._heartbeat()))
                self._session_tasks.append(asyncio.ensure_future(self._keepalive()))
                logging.info("UserWSSession started for %s", self.trade_id)

    async def _ws_error(self, ex):
        if self.operational_status is not None:
            self._try_count += 1
            delay = random.randint(1, 5) * self._try_count
            logging.error(f"UserWSSession restart: delay: {delay}s, {ex}")
            await asyncio.sleep(delay)
            asyncio.ensure_future(self.start())

    async def handle_request(self, method: str, params: {} = None, api_key=False, signed=False):
        """
        Construct and handling request/response to WS API endpoint, use a description of the methods on
        https://developers.binance.com/docs/binance-trading-api/websocket_api#request-format
        :param method: 'method'
        :param params: 'params'
        :param api_key: True if API key must be sent
        :param signed: True if signature must be sent
        :return: result: {} or None if temporary Out-of-Service state
        """
        if not self.operational_status:
            logging.warning("UserWSSession operational status is %s", self.operational_status)
            return None
        elif method in ('order.place', 'order.cancelReplace') and not self.order_handling:
            logging.warning("UserWSSession: exceeded order placement limit, try later")
            return None
        else:
            _id = f"{self.trade_id}-{method.replace('.', '_')}"[-36:]
            queue = self._queue.setdefault(_id, asyncio.Queue())
            req = {'id': _id, "method": method}
            if (api_key or signed) and not params:
                params = {}
            if api_key:
                params['apiKey'] = self._api_key
            if signed:
                params['timestamp'] = int(time.time() * 1000)
                payload = '&'.join(f"{key}={value}" for key, value in dict(sorted(params.items())).items())
                params['signature'] = generate_signature('binance_ws', self._api_secret, payload)
            if params:
                req['params'] = params
            await self._send_request(req)
            try:
                res = await asyncio.wait_for(queue.get(), timeout=TIMEOUT)
            except asyncio.TimeoutError:
                ex = "UserWSSession timeout error"
                await self._ws_error(ex)
            except asyncio.CancelledError:
                pass  # Task cancellation should not be logged as an error
            else:
                return self._handle_msg_error(res)

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
                    logging.warning("UserWSSession._keepalive: %s", ex)
                else:
                    if not self.operational_status:
                        self.operational_status = True
                        logging.info("UserWSSession operational status restored")
                    else:
                        self.order_handling = True
                        logging.info("UserWSSession order limit restriction was cleared")
        logging.warning(f"UserWSSession: keepalive loop stopped for {self.trade_id}")

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
        logging.info("STOP User WSS for %s", self.trade_id)
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

    async def _send_request(self, req: {}):
        try:
            await self._web_socket.send_json(req)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except RuntimeError as ex:
            await self._ws_error(ex)
        except Exception as ex:
            logging.error("UserWSSession._send_request: %s", ex)

    async def _receive_msg(self):
        while self.operational_status is not None:
            msg = await self._web_socket.receive_json()
            self._handle_rate_limits(msg.pop('rateLimits', []))
            queue = self._queue.get(msg.get('id'))
            if queue:
                await queue.put(msg)
            else:
                logging.warning("Can't get queue for transporting message: %s", msg)

    def _handle_msg_error(self, msg):
        if msg.get('status') != 200:
            error_msg = msg.get('error')
            logging.error(f"UserWSSession get error: {error_msg}")
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
            #
            endpoint = config['endpoint'][exchange]
            #
            ws_api = endpoint.get('ws_api_test') if test_net else endpoint.get('ws_api')
            #
            return exchange, test_net, api_key, api_secret, ws_api
    raise UserWarning(f"Can't find account '{_account_name}' defined in {CONFIG_FILE}")
