<h1 align="center"><img align="center" src="https://user-images.githubusercontent.com/77513676/250364389-cbedc171-a930-4467-a0cd-21627a6a41ed.svg" width="75">Crypto WS API connector for ASYNC requests</h1>

<h2 align="center">Full coverage of all methods provided by the interface</h2>

<h3 align="center">Provides of connection management, keepalive and rate limits control</h3>

***
<h1 align="center"><a href="https://pypi.org/project/crypto-ws-api/"><img src="https://img.shields.io/pypi/v/crypto-ws-api" alt="PyPI version"></a>
<a href="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api.svg/?label=resolved+issues&token=TXghPzbi0YWhkCLU8Q1tmDyQ"/></a>
<a href="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api.svg/?label=active+issues&token=TXghPzbi0YWhkCLU8Q1tmDyQ"/></a>
<a href="https://sonarcloud.io/summary/new_code?id=DogsTailFarmer_crypto-ws-api" target="_blank"><img alt="sonarcloud" title="sonarcloud" src="https://sonarcloud.io/api/project_badges/measure?project=DogsTailFarmer_crypto-ws-api&metric=alert_status"/></a>
<a href="https://pepy.tech/project/crypto-ws-api" target="_blank"><img alt="Downloads" title="Downloads" src="https://static.pepy.tech/badge/crypto-ws-api"/></a>
</h1>

***
For :heavy_check_mark:[Binance](https://accounts.binance.com/en/register?ref=FXQ6HY5O), :heavy_check_mark:[OKX](https://okx.com/join/2607649), :heavy_check_mark:[Bitfinex](https://www.bitfinex.com/sign-up?refcode=v_4az2nCP), :heavy_check_mark:[HTX](https://www.htx.com/invite/en-us/1f?invite_code=9uaw3223)
***

## Features
Lightweight and efficient solution to utilize of all available methods** provided through the:
* [Binance Websocket API v3](https://binance-docs.github.io/apidocs/websocket_api/en)
* [OKX Websocket API v5](https://www.okx.com/docs-v5/en/#overview-websocket)
* [Bitfinex Websocket Inputs](https://docs.bitfinex.com/reference/ws-auth-input)
* [HTX WS Trade](https://www.htx.com/en-us/opend/newApiPages/?id=8cb89359-77b5-11ed-9966-1928f079ab6)

** Not for channel by one-way subscription, for **_request <-> response_** mode only

### Session management layer for:
- Credentials
- Connection
- Keepalive
- Error handling
- Limits control
- Methods construction
  + Creating request on-the-fly from method name and params: {}
  + Generating signature if necessary
  + Response handling
- logging

### User interface layer
- Start session instance
- Send async request
- Get response or raised exception
- Reuse instance for different type requests
- Stop session instance

## Get started
### Install use PIP

```console
pip install crypto_ws_api
```
For upgrade to latest versions use:
```console
pip install -U crypto_ws_api
```

After first install create environment by run 
```console
crypto_ws_api_init
```
in terminal window.

The config directory will be created. You get path to config:

>ubuntu@ubuntu:~$ crypto_ws_api_init
> 
>Can't find config file! Creating it...
> 
>Before first run set account(s) API key into /home/ubuntu/.config/crypto_ws_api/ws_api.toml

### Prepare exchange account
* For test purpose log in at [Binance Spot Test Network](https://testnet.binance.vision/)

For OKX and Bitfinex, unlike Binance, a limited number of methods are implemented at the WS API level,
such as creating, modifying, and deleting orders.
There are no public get-time (), ping-pong, etc., so this demo script is limited to calling Binance
to demonstrate capabilities.

* Create API Key
* After install and create environment specify api_key and api_secret to the config file

### Start demo
* Run in terminal window
```
crypto_ws_api_demo
``` 

## Useful tips

_*`crypto_ws_api/demo.py` - complete and fully functional example*_

### Get credentials and create user session

```bazaar
from crypto_ws_api.ws_session import UserWSSession

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
```

### Method example
```bazaar
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
        logger.error(f"Handling exception: {_ex}")
    else:
        logger.info(f"Account information (USER_DATA) response: {res}")
```

### Demo method's calling
```bazaar
await account_information(user_session, trade_id)
```

### Stop user session and close aiohttp session
```bazaar
await user_session.stop()
await session.close()
```

### Create limit order example
```bazaar
if self.exchange == 'binance':
    params = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "price": "23416.10000000",
        "quantity": "0.00847000",
    }
    binance_res = await user_session.handle_request(trade_id, "order.place", params, _api_key=True, _signed=True)

elif self.exchange == 'bitfinex':
    params = {
        "type": "EXCHANGE LIMIT",
        "symbol": "tBTCUSDT",
        "price": "23416.10000000",
        "amount": ('' if side == 'BUY' else '-') + "0.00847000",
    }
    bitfnex_res = await user_session.handle_request(trade_id, "on", params)

elif self.exchange == 'okx':
    params = {
        "instId": "BTC-USDT",
        "tdMode": "cash",
        "clOrdId": "client_order_id",
        "side": "buy",
        "ordType": "limit",
        "sz": "0.00847000",
        "px": "23416.10000000",
    }
    okx_res = await user_session.handle_request(trade_id, "order", params)
```

### Logging setup
For configure logging in multi-module project use next snippet for yours `main()`:
```bazaar
import logging.handlers

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
```

## [Limits control](https://developers.binance.com/docs/binance-trading-api/websocket_api#general-information-on-rate-limits) :link:
Upon reaching the limit threshold of each type, the session switches to the Out-of-Service state.
If you send a request in this state, the answer will be `None`

*In any case, you are protected from exceeding limits and blocking for this reason*

## Donate
*USDT* (TRC20) TU3kagV9kxbjuUmEi6bUym5MTXjeM7Tm8K
