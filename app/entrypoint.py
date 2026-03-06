"""Entrypoint — runs Telegram bot + web app in a single process."""
import threading
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("entrypoint")


def start_web():
    from web import app
    log.info("Starting web app on port 5001...")
    app.run(host="0.0.0.0", port=5001, debug=False)


def start_bot():
    from telegram_bot import main
    log.info("Starting Telegram bot...")
    main()


if __name__ == "__main__":
    threading.Thread(target=start_web, daemon=True).start()
    start_bot()
