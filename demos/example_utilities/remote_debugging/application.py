from .client import application as client_application
from .server import application as server_application


def run():
    result = input("Choose peer type: Server(s), Client(c)\n>>>")
    applications = {'c': client_application, 's': server_application}
    application = applications[result.lower().strip()]()