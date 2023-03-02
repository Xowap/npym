# NPyM

NPyM is a service that translates NPM packages into Python wheels so that you
can install them using a Python package manager. This helps calling JS code from
Python, especially if you combine it with
[Node Edge](https://node-edge.readthedocs.io/en/latest/).

This package is a support package for NPyM, which is depended upon by the
converted NPM packages.

It provides:

-   A wrapper to allow JS bin to be installed by package managers
-   A way to know where the `node_modules` is installed

In order to know this, you can easily do:

```python
from npym import node_modules

print(node_modules)
```
