
<p align="center"><img src="https://user-images.githubusercontent.com/77513676/250364389-cbedc171-a930-4467-a0cd-21627a6a41ed.svg" width="250"></p>

***
<h1 align="center">Crypto WS API connector for ASYNC requests</h1>

<h2 align="center">Full coverage of all methods provided by the interface</h2>

<h3 align="center">Provides of connection management, keepalive and rate limits control</h3>

***
Badges place here
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

After first install create environment by run ```crypto_ws_api_init``` in terminal window.

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

## Useful tips (see `demo.py` for reference)
### Get credentials and create user session

```bazaar
session = aiohttp.ClientSession()
exchange, test_net, api_key, api_secret, ws_api_endpoint = get_credentials(account_name)

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
```

### [Limits control](https://developers.binance.com/docs/binance-trading-api/websocket_api#general-information-on-rate-limits)
Upon reaching the limit threshold of each type, the session switches to the Out-of-Service state. Monitor the values
of the variables `user_session.operational_status` and `user_session.order_handling`

If you send a request in this state, the answer will be `None`

*In any case, you are protected from exceeding limits and blocking for this reason*

## Donate
*BNB*, *BUSD*, *USDT* (BEP20) 0x5b52c6ba862b11318616ee6cef64388618318b92

*USDT* (TRC20) TP1Y43dpY7rrRyTSLaSKDZmFirqvRcpopC
