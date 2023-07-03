
<p align="center"><img src="https://user-images.githubusercontent.com/77513676/250364389-cbedc171-a930-4467-a0cd-21627a6a41ed.svg" width="250"></p>

***
<h1 align="center">Crypto WS API connector for ASYNC requests</h1>

<h2 align="center">Full coverage of all methods provided by the interface</h2>

<h3 align="center">Provides of connection management, keepalive and rate limits control</h3>

***
<a href="https://badge.fury.io/py/crypto-ws-api"><img src="https://badge.fury.io/py/crypto-ws-api.svg" alt="PyPI version"></a>
<a href="https://codeclimate.com/github/DogsTailFarmer/crypto-ws-api/maintainability"><img src="https://api.codeclimate.com/v1/badges/2d2a654ba393eb88d911/maintainability" /></a>
<a href="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api.svg/?label=resolved+issues&token=TXghPzbi0YWhkCLU8Q1tmDyQ"/></a>
<a href="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://app.deepsource.com/gh/DogsTailFarmer/crypto-ws-api.svg/?label=active+issues&token=TXghPzbi0YWhkCLU8Q1tmDyQ"/></a>
<a href="https://sonarcloud.io/summary/new_code?id=DogsTailFarmer_crypto-ws-api" target="_blank"><img alt="sonarcloud" title="sonarcloud" src="https://sonarcloud.io/api/project_badges/measure?project=DogsTailFarmer_crypto-ws-api&metric=alert_status"/></a>
<a href="https://pepy.tech/project/crypto-ws-api" target="_blank"><img alt="Downloads" title="Downloads" src="https://static.pepy.tech/badge/crypto-ws-api"/></a>
***
For :heavy_check_mark:Binance, 
***

## Features
Lightweight and efficient solution to utilize of all available methods provided through the:
* [Binance Websocket API v3](https://developers.binance.com/docs/binance-trading-api/websocket_api)

### Session management layer for:
- Credentials
- Connection
- Keepalive
- Error handling
- Limits control
- Methods construction
  + Generating session request id by default
  + Creating request on-the-fly from method name and params: {}
  + Generating signature if necessary
  + Response handling
- logging

### User interface layer
- Start session instance
- Getting session operational status
- Send async request
- Get response or raised exception
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

The config directory will be created. You get path to config `ws_api.toml`

### Prepare exchange account
* For test purpose log in at [Binance Spot Test Network](https://testnet.binance.vision/)
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
from crypto_ws_api.ws_session import get_credentials, UserWSSession

session = aiohttp.ClientSession()
_exchange, _test_net, api_key, api_secret, ws_api_endpoint = get_credentials(account_name)

user_session = UserWSSession(
    api_key,
    api_secret,
    session=session,
    endpoint=ws_api_endpoint
)

await user_session.start()
print(f"Operational status: {user_session.operational_status}")
```
### Demo method's calling
```bazaar
await account_information(user_session)
```

### Stop user session and close aiohttp session
```bazaar
await user_session.stop()
await session.close()
print(f"Operational status: {user_session.operational_status}")
```

### Method call example
```bazaar
async def account_information(user_session: UserWSSession):
    # https://developers.binance.com/docs/binance-trading-api/websocket_api#account-information-user_data
    try:
        res = await user_session.handle_request(
            "account.status",
            api_key=True,
            signed=True
        )
        if res is None:
            print("Here handling state Out-of-Service")
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except Exception as _ex:
        print(f"Handling exception: {_ex}")
    else:
        print(f"Account information (USER_DATA) response: {res}")
```

### [Limits control](https://developers.binance.com/docs/binance-trading-api/websocket_api#general-information-on-rate-limits) :link:
Upon reaching the limit threshold of each type, the session switches to the Out-of-Service state. Monitor the values
of the variables `user_session.operational_status` and `user_session.order_handling`

If you send a request in this state, the answer will be `None`

*In any case, you are protected from exceeding limits and blocking for this reason*

## Donate
*BNB*, *BUSD*, *USDT* (BEP20) 0x5b52c6ba862b11318616ee6cef64388618318b92

*USDT* (TRC20) TP1Y43dpY7rrRyTSLaSKDZmFirqvRcpopC
