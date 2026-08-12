# End-to-End Example: `pigeon`

This guide shows the complete upload workflow:

1. Start `pigeon-dispatch` (application-side logic).
2. Start `pigeon-server` (gateway/upload API).
3. Run `pigeon-client` (user upload command).

By the end, you should see an uploaded file and dispatch state on disk.

From repo root:

```bash
cd example
source /home/aravind/laab/tools/pigeon/venv/bin/activate
```

## What You Need

- A Python environment with all three packages installed:
  - `pigeon-client`
  - `pigeon-server`
  - `pigeon-dispatch`
- Three terminals (recommended).
- A test data directory to upload.


## Step 1: Start Dispatch (Terminal 1)

```bash
./run_dispatch.sh
```

What this does:

- Starts dispatch on `http://127.0.0.1:5001`.
- Creates/uses `example/test-data` to store:
  - `state.json` (request lifecycle state)
  - uploaded files from the flow

## Step 2: Start Server (Terminal 2)

```bash
./run_server.sh
```

What this does:

- Starts `pigeon-server` on `http://127.0.0.1:5000`.
- Uses `PIGEON_DISPATCH_URL` to call dispatch.
- Uses matching `PIGEON_DISPATCH_KEY` so dispatch accepts requests.

## Step 3: Upload Data from Client (Terminal 3)

```bash
./run_client_upload.sh
```

Expected client output:

```text
Upload successful
```

## Step 4: Verify Result

Inspect dispatch output directory:

```bash
ls -la ./test-data
cat ./test-data/state.json
```

You should see:

- a `.bin` file for your request id
- status updated in `state.json` (for a successful flow, typically `received`)

## Why These Values Matter

- `--key 123-demo`: The example backend accepts keys starting with `123`.
- `PIGEON_DISPATCH_KEY`: Must match in both dispatch and server.
- `PIGEON_DISPATCH_URL`: Tells server where dispatch is running.
- `PIGEON_SERVER_URL`: Tells client where server is running.

Script defaults (can be overridden by env vars):

- `run_dispatch.sh`: `PIGEON_DISPATCH_DIR=./test-data`, `PIGEON_DISPATCH_KEY=supersecretkey`
- `run_server.sh`: `PIGEON_TOKEN_KEY=test-key`, `PIGEON_DISPATCH_KEY=supersecretkey`, `PIGEON_DISPATCH_URL=http://127.0.0.1:5001`, `PIGEON_PORT=5000`
- `run_client_upload.sh`: `PIGEON_SERVER_URL=http://127.0.0.1:5000`, `key=123-demo`, `sample_dir=./sample-data`

## Troubleshooting

- If client fails with key validation:
  - Use an object key starting with `123` in this example backend.
- If server cannot reach dispatch:
  - Check `PIGEON_DISPATCH_URL` and that dispatch is running on port `5001`.
- If dispatch says unauthorized:
  - Ensure `PIGEON_DISPATCH_KEY` is identical in Terminal 1 and Terminal 2.
