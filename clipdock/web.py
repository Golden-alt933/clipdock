"""Container entry point for the hosted website."""
import os


def main():
    os.environ["CLIPDOCK_HOSTED"] = "1"
    os.environ.setdefault("CLIPDOCK_DATA_DIR", "/tmp/clipdock")
    import uvicorn
    from .app import app

    server = uvicorn.Server(uvicorn.Config(
        app, host="0.0.0.0", port=int(os.environ.get("PORT", "10000")),
        workers=1, log_level="warning", access_log=False,
        proxy_headers=True, forwarded_allow_ips="*",
    ))
    app.state.server = server
    server.run()


if __name__ == "__main__":
    main()
