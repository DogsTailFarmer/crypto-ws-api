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
