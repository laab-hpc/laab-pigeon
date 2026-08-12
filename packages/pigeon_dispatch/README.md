# pigeon-dispatch

`pigeon-dispatch` is the dispatch component of `pigeon` used by the web application to define upload validation and post-upload processing behavior.
Install this package at the application endpoint where you want to enforce object-key rules and decide how uploaded data is handled.


## Runtime Configuration

`pigeon-dispatch` requires the following environment variable.

### Required variable

- `PIGEON_DISPATCH_KEY`: Secret key shared between server and dispatch.
  This ensures only `pigeon-server` can contact dispatch endpoints.

## Backend Interface

You need to implement `DispatchBackend` in your application and register the blueprint created by `create_dispatch_blueprint(...)`.
The backend is where you define the core logic for:

- `validate_object_key(object_key)`: Reject invalid upload intents early.
- `generate_request_id(object_key)`: Create a request id for the upload flow.
- `register_token(request_id, issued_at, expires_at)`: Persist token validity window.
- `get_dispatch_info(request_id)`: Return where data should go (`filesystem` path or `api` endpoint).
- `on_notification(request_id, status, message)`: Receive final status from `pigeon-server`.

For example, `SimpleFileDispatchBackend` in this repository provides a reference implementation to guide your own backend design. 

## API Endpoints

These are the endpoints available to `pigeon-server`.

- `POST /generate-request-id`
- `POST /register-token`
- `POST /get_dispatch_info`
- `POST /notification`

## Example

Run the included example dispatch app:

```bash
cd example
export PIGEON_DISPATCH_DIR="./test-data"
export PIGEON_DISPATCH_KEY="supersecretkey"
python dispatch_app.py
```

This starts a dispatch service on port `5001` that `pigeon-server` can call during the upload workflow.
In this example, `PIGEON_DISPATCH_DIR` is used by `SimpleFileDispatchBackend` to store state and uploaded files.
