# npym

NPyM is a bridge between NPM and Pypi. It will let you install JS dependencies
using a Python package manager.

## Installation & Usage

This project is built upon [Model W](https://model-w.rtfd.io/). Hence, all
conventions apply.

In particular this was created using the
[Project Maker](https://github.com/ModelW/project-maker).

> **Note** &mdash; Don't forget to read the part about
> [Django Models Customization](https://github.com/modelw/project-maker#django-models-customization).

## Documentation

The documentation of this project follows the
[Code Guidelines](https://with-codeguidelines.readthedocs-hosted.com/en/latest/documentation.html)
from WITH.

### Components

This project is composed of the following components:

-   [API](./api) &mdash; The back-end of the project, mostly serving as API and
    back-office admin. Most of the time, URLs targeting the API are prefixed by
    `/back`.

More components might pop up in the future and we're following the standard
Model&mdash;W structure for now, so that's why it looks a bit weird.
