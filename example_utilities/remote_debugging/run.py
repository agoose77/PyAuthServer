from .server import application as server_application
from .client import application as client_application


def run():
    result = input("Which application? [S for server | C for client]. Lowercase supported").lower()

    if result == "s":
        server_application()

    elif result == "c":
        client_application()