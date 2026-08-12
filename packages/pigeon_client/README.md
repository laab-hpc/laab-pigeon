# pigeon-client

`pigeon-client` is the CLI component of `pigeon` used by end users to interact with the web application (the **dispatch** service).
Install this package at the user endpoint (for example, a login node, workstation, or any machine where users run uploads), then use it to package and upload data through `pigeon-server`.


## Command-Line Arguments

Use `-h` at any level to see built-in help:

```bash
pigeon-client -h
pigeon-client push -h
```

### Global arguments

- `-v`, `--verbose`: Increase log verbosity (`-v` for `INFO`, `-vv` for `DEBUG`).
  This is useful for understanding each step (URL generation, archive creation, upload) when debugging connectivity or validation issues.

### Subcommand: `push`

Uploads a directory.

- `-k`, `--key` (required): Object key sent to the server to identify/validate the upload request.
  Think of this as the upload intent identifier. Dispatch uses it to decide whether this upload is allowed and how it should be routed/processed.
- `-d`, `--data-dir` (required): Directory to archive and upload.
  This tells the client exactly which local dataset to pack into a `.tar.gz` before sending.
- `--server-url` (optional): Base URL of `pigeon-server`. If omitted, uses `PIGEON_SERVER_URL`.
  This selects the target `pigeon-server` instance. Keeping it optional lets users set one default in their shell environment and avoid repeating it.

## Example

```bash
export PIGEON_SERVER_URL="https://pigeon-llview.fz-juelich.de/"

pigeon-client -v push \
  --key 123-userA-input \
  --data-dir ./sample_data
```

Expected success output:

```text
Upload successful
```

A successful upload means the dispatch service has processed your data. For example, if using LLview as the dispatch service, it will process the uploaded data and make results available in the job reports.
