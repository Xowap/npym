# API

This handles the API.

All the URLs pointing to this are prefixed by `/back`.

## Components

You'll find the following apps:

-   [people](./npym/apps/people) &mdash; The user model and authentication.

## OpenAPI

When the app is in development mode, you can access the OpenAPI documentation at
`/back/api/schema/redoc/`.

This documentation is auto-generated using
[drf-spectacular](https://drf-spectacular.readthedocs.io/en/latest/). As you
create more APIs, make sure that they render nicely in OpenAPI format.
