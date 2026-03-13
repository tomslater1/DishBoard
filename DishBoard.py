import os
import sys

import certifi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from utils.app_runtime import ApplicationController
from utils.paths import get_resource_path

QSS_PATH = get_resource_path("assets/styles/theme.qss")
ICON_PATH = get_resource_path("assets/icons/DishBoard-darkicon.png")
ICON_DOCK_PATH = get_resource_path("assets/icons/DishBoard-darkicon.png")


def main():
    controller = ApplicationController(
        qss_path=QSS_PATH,
        icon_path=ICON_PATH,
        icon_dock_path=ICON_DOCK_PATH,
        resource_path_fn=get_resource_path,
    )
    raise SystemExit(controller.run())


if __name__ == "__main__":
    main()
