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
