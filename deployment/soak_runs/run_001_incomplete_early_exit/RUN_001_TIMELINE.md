# Run 001 timeline

Run 001 started at `2026-08-31T13:18:31Z` as PowerShell PID 2416 with a 120-minute target and 5-minute sample interval. It wrote nine coherent samples through `2026-08-31T13:59:26Z` (`40.91` minutes), all with HTTP 200, worker ONLINE, and no recorded errors.

Windows recorded EventLog 6006 at `14:04:06Z`, Kernel-Power Event 109 (`Power Action Reboot`) at `14:04:11Z`, and EventLog 6005 at `14:04:35Z`. The runner was absent after recovery. No runner terminal marker, exception, or non-empty stderr was recorded.

Conclusion: `INCOMPLETE_EARLY_EXIT`, with high-confidence bounded cause `WINDOWS_SLEEP_OR_RESTART` / system reboot interruption. This is not evidence of a ResearchNavigator API, worker, tunnel, or database failure.
