from network import NetworkError


class AuthError(NetworkError):
    pass


class BlacklistError(NetworkError):
    pass
