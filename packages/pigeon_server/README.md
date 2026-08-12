# pigeon-server

`pigeon-server` is the Flask API component of `pigeon` that sits between `pigeon-client` and your web application (the **dispatch** service).
Install this package at whichever endpoint should receive user uploads, validate short-lived tokens, and forward data to dispatch for final processing.
This can be the same host as dispatch, or a separate gateway/edge server.


## Runtime Configuration

`pigeon-server` requires the following environment variables.

### Required variables

- `PIGEON_TOKEN_KEY`: Secret used to sign upload tokens.
  This protects upload URLs from tampering and allows the server to verify that a token is authentic.
- `PIGEON_DISPATCH_KEY`: Secret key shared between server and dispatch.
  This ensures only your trusted server can call internal dispatch endpoints.
- `PIGEON_DISPATCH_URL`: URL where `pigeon-dispatch` is running.
  The server calls dispatch for request validation, routing info, and completion notifications.

### Optional variables

- `PIGEON_TOKEN_AGE` (default: `600`): Token lifetime in seconds.
  Shorter values reduce replay risk; longer values tolerate slower clients/uploads.
- `PIGEON_SERVER_PORT` (default: `5000`): Port where `pigeon-server` listens.
- `PIGEON_SERVER_MOUNT` (default: `/`): URL mount prefix for server routes.
  Use this when hosting behind a reverse proxy under a subpath.

## API Endpoints

These are the endpoints available to `pigeon-client`.

- `POST /generate-upload-url`: Accepts `object_key`, validates via dispatch, and returns a temporary upload URL.
- `POST /upload/<token>`: Accepts `application/octet-stream` upload and forwards/stores bytes based on dispatch instructions.

## Example

```bash
export PIGEON_TOKEN_KEY="change-me-token-secret"
export PIGEON_DISPATCH_KEY="change-me-dispatch-secret"
export PIGEON_DISPATCH_URL="http://127.0.0.1:5001"
export PIGEON_PORT="5000"

pigeon-server
```

When running, this service becomes the upload entry point used by `pigeon-client`, while dispatch remains responsible for validating keys and deciding final processing behavior.
