# Security policy

## Supported version

Security fixes are made against the latest release.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature rather than opening a public issue.

## Data model

BenchLog stores records locally under `.benchlog/`. On POSIX systems it creates metadata
directories with mode `0700` and captured files with mode `0600`. It executes commands directly,
without a shell, and never records the complete process environment. Only variables named with
`--env` are captured.

Configuration files, logs, metrics, command arguments, working paths, and explicitly selected
artifacts may still contain sensitive material. Review them before sharing a `.benchlog` directory.
BenchLog records Git commit metadata and dirty state, but it does not capture remotes or diffs.
