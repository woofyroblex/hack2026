from uuid import uuid4
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from notifications.services import queue_email
from accounts.throttling import PasswordRecoveryThrottle


def change_password(user, password):
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({'password': exc.messages})
    user.set_password(password)
    user.save(update_fields=['password'])
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordRecoveryThrottle]

    def post(self, request):
        email = serializers.EmailField().run_validation(request.data.get('email'))
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            base = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
            queue_email('password_reset', user.email, {'reset_url': f'{base}/#reset-password?uid={uid}&token={token}'}, f'password-reset:{uuid4()}')
        return Response({'message': 'If an account exists for that email, a reset link will be sent.'}, status=202)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordRecoveryThrottle]

    @transaction.atomic
    def post(self, request):
        try:
            pk = urlsafe_base64_decode(request.data.get('uid', '')).decode()
            user = get_user_model().objects.select_for_update().get(pk=pk, is_active=True)
        except (ValueError, TypeError, UnicodeDecodeError, OverflowError, get_user_model().DoesNotExist):
            raise serializers.ValidationError({'token': 'This reset link is invalid or expired.'})
        if not default_token_generator.check_token(user, request.data.get('token', '')):
            raise serializers.ValidationError({'token': 'This reset link is invalid or expired.'})
        password = serializers.CharField(trim_whitespace=False, max_length=128).run_validation(request.data.get('password'))
        change_password(user, password)
        return Response({'message': 'Password updated. Sign in with your new password.'})


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if not user.check_password(request.data.get('current_password', '')):
            raise serializers.ValidationError({'current_password': 'Current password is incorrect.'})
        password = serializers.CharField(trim_whitespace=False, max_length=128).run_validation(request.data.get('password'))
        change_password(user, password)
        return Response({'message': 'Password updated. Sign in again.'})
