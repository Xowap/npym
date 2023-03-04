# NPyM Info

This is an utility package to help you know if you are running in a NPyM
environment.

## Installation

```bash
npm install @npym/info
```

## Usage

```js
import { isNpym } from "@npym/info";

if (isNpym()) {
    console.log("This is a NPyM environment");
}
```
