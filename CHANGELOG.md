## 2.1.0 - 2025-06-22
✨ refactor(ws_session.py): simplify `ws_login` and `request` methods by removing redundant `send_api_key` parameter.

## 2.0.21 - 2025-06-22
🔧 fix(README.md): Improve documentation layout for better readability  
🔧 fix(ws_session.py): Handle `asyncio.CancelledError` gracefully in `start_wss` method  
🔧 fix(ws_session.py): Replace `asyncio.CancelledError` with `KeyboardInterrupt` exception in `handle_request` method  
🔧 fix(demo.py): Remove unnecessary `asyncio.CancelledError` handling to clean up error logging  
🔧 fix(ws_api.toml.template): Update testnet URL for Binance websocket API 

## 2.0.20 - 2025-04-24
* On `Binance` now API key type [Ed25519](https://www.binance.com/en/support/faq/detail/6b9a63f1e3384cf48a2eedb82767a69a) is used instead of `HMAC`
✨ feat(ws_session): implement `compose_binance_ws_auth` for Binance WebSocket authentication  
🔧 fix(ws_session): update `generate_signature` for improved signature handling  
🔧 fix(ws_session): handle `None` return in `request` method  
🚀 chore(requirements): add `cryptography` dependency for signature handling  
🔧 fix(pyproject): require Python version 3.10 or higher  

## 2.0.19 - 2025-03-28
### Fix
* `ws_session.ws_login`: Incorrect exit from authentication procedure in case of unsuccessful attempt

## 2.0.18 - 2025-03-10
### Fix
* [🔒] fix/ws_session.py: Proper restoration of WebSocket connection during recurring failures

### Update
* [💻] feat/ws_session.py: Add logging configuration and handlers for debug purpose
* [🔄] fix/ws_session.py: Update UserWSS class to accept a logger instance

## 2.0.17 - 2025-02-20
### Update
* Bump dependencies

## 2.0.16 - 2024-12-27
* `websockets`: bump to v14.2

## 2.0.15 - 2024-12-16
### Added for new features
* `HTX` implemented

### Update
* reused WS connection grouped by private and public methods
* `websockets`: bump to v14.1
* some minor improvements

## 2.0.14 - 2024-09-13
### Update
* `pyproject.toml`

## 2.0.13 - 2024-09-13
### Update
* Dependencies

## 2.0.12 - 2024-06-26
### Update
* Dependencies

## 2.0.11 - 2024-04-30
### Update
* Some minor improvement

## 2.0.10 - 2024-04-19
### Update
* Some minor improvement

## 2.0.9 - 2024-04-14
### Fix
* Creating asynchronous tasks done right

## 2.0.8 - 2024-03-31
### Fix
* tons log records: `websockets socket.send() raised exception.`

## 2.0.7 - 2024-03-25
### Update
* Refactoring and some minor fixes

## 2.0.6 - 2024-01-05
### Update
* replacing json with ujson to improve performance

## 2.0.5.post3 - 2023-11-01
### Update
* Dependencies updated
* Some minor fixes

## 2.0.5 - 2023-10-31
### Update
* Some minor fixes

## 2.0.4 - 2023-10-09
### Update
* Refine connection management

## 2.0.3.post1 - 2023-10-05
### Fix
* Timeout killed an infinite loop of waiting for a connection, gives a quick response to use the REST API alternative

## 2.0.3 - 2023-09-30
### Fix
* Fixed synchronization problems with multiple connection opening and registration

### Update
* Error handling: some improvements

## 2.0.2.post1.dev2
### Fix
* Bitfinex: [2023-09-22 08:06:28,268: WARNING] Malformed request: status: {'event': 'error', 'msg': 'auth: dup', 'code': 10100}

## 2.0.2.post1.dev1
### Fix
* [OKX: Send request before log in when restart WS](https://github.com/DogsTailFarmer/crypto-ws-api/issues/2#issue-1906963265)

## v2.0.2 - 2023-09-19
### Added for new features
* Managed delay added for new connection

## v2.0.1b6 - 2023-09-15
### Update
* Migrated from aiohttp.ws_connection to websockets.client

## v2.0.1 - 2023-08-24
### Update
* Some minor fixes

## v2.0.1b5 - 2023-07-18
### Fix
* [ RuntimeError: dictionary changed size during iteration #1 ](https://github.com/DogsTailFarmer/crypto-ws-api/issues/1#issue-1857274697)

## 2.0.0rc1 - 2023-08-08
### Added for new features
* Bitfinex implemented

### Update
* The general concept is saved - the request is formed "on the fly" from the type and parameters, so no additional
description of the methods is required
* For each request type, its own WS handle instance is created
* WS handle instance are reusable
* Excluded _race_ when creating WS handle instance when receiving a packet of the same type of requests
* README.md

## v1.0.2b2 - 2023-07-26
### Added for new features
* OKX implemented

## v1.0.1-1 - 2023-07-05
### Update
* README.md
* UserWSSession.__init__(): check parameters 

## v1.0.1 - 2023-07-04
### Fix
* Added SYMBOL for query ID

### Update
* `ws_session.py`: set logging for multi-module purpose
* `demo.py`: configure logging example
* `README.md`
