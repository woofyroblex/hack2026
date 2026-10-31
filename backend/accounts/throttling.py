from rest_framework.throttling import AnonRateThrottle


class TrustedProxyAnonRateThrottle(AnonRateThrottle):
    """Use the client address supplied by the app's trusted reverse proxy."""

    def get_ident(self, request):
        client_address = request.META.get('HTTP_X_REAL_IP')
        return client_address or super().get_ident(request)


class AuthenticationThrottle(TrustedProxyAnonRateThrottle):
    scope = 'auth'


class PasswordRecoveryThrottle(TrustedProxyAnonRateThrottle):
    scope = 'password_recovery'
