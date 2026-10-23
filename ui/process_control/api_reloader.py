"""Development API: runs uvicorn in a child process and restarts it whenever a
Python file under the app folder changes (watchfiles).

Used instead of ``uvicorn --reload``: on Windows that one restarts the server
with a Ctrl+C, which never arrives in a process started without a console
window (like the ones of the Backend panel), so the reload hangs. watchfiles
stops the old server by terminating it directly.

    python ui/process_control/api_reloader.py <app> <app_dir> <host> <port>
"""
import sys

import watchfiles

if __name__ == "__main__":
    app, app_dir, host, port = sys.argv[1:5]
    watchfiles.run_process(
        app_dir,
        target="uvicorn.run",
        kwargs={"app": app, "app_dir": app_dir, "host": host, "port": int(port)},
        watch_filter=watchfiles.PythonFilter(),
    )
