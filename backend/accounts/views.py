from django.contrib.auth import authenticate, get_user_model, password_validation
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from uuid import uuid4
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from customers.models import Customer
from customers.serializers import CustomerSerializer
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from django.middleware.csrf import get_token
from django.utils.crypto import constant_time_compare
from accounts.authentication import password_stamp


def _api_error(code, message, *, fields=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'code': code, 'message': message, 'fields': fields or {}}, status=status_code)


def _user_payload(user):
    full_name = user.get_full_name().strip()
    role = 'admin' if user.is_superuser else 'staff' if user.is_staff else 'customer'
    try:
        customer = user.customer_profile
    except (AttributeError, Customer.DoesNotExist):
        customer = None
    customer_payload = None
    if customer is not None:
        customer_payload = {
            'id': customer.pk,
            'name': customer.name,
            'email': customer.email,
            'company': customer.company,
            'phone': customer.phone,
            'billing_address': CustomerSerializer(customer).data.get('billing_address'),
            'created_at': customer.created_at.isoformat(),
        }
    return {
        'id': user.pk,
        'email': user.email,
        'full_name': full_name,
        'name': full_name or user.get_username(),
        'role': role,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'is_active': user.is_active,
        'customer': customer_payload,
    }


def _with_refresh_cookie(response, token, remember_me=False):
    options = {
        'key': 'refresh_token',
        'value': str(token),
        'httponly': True,
        'secure': bool(settings.SESSION_COOKIE_SECURE),
        'samesite': 'Lax',
        'path': '/api/v1/auth/',
    }
    if remember_me:
        options['max_age'] = int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds())
    response.set_cookie(**options)
    return response


def _issue_tokens(user, remember_me=False):
    refresh = RefreshToken.for_user(user)
    refresh['remember_me'] = bool(remember_me)
    refresh['password_stamp'] = password_stamp(user)
    response = Response({'access_token': str(refresh.access_token), 'user': _user_payload(user)})
    return _with_refresh_cookie(response, refresh, remember_me)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        password = request.data.get('password', '')
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        authenticated = authenticate(request, username=user.get_username(), password=password) if user else None
        if authenticated is None:
            return _api_error('INVALID_CREDENTIALS', 'Invalid email or password.', status_code=status.HTTP_401_UNAUTHORIZED)
        get_token(request._request)
        return _issue_tokens(authenticated, bool(request.data.get('remember_me', False)))


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        full_name = str(request.data.get('full_name', '')).strip()
        password = request.data.get('password', '')
        if not email or '@' not in email:
            return _api_error('VALIDATION_ERROR', 'The request could not be completed.', fields={'email': ['Enter a valid email address.']})
        try:
            validate_email(email)
        except ValidationError:
            return _api_error('VALIDATION_ERROR', 'The request could not be completed.', fields={'email': ['Enter a valid email address.']})
        if not full_name:
            return _api_error('VALIDATION_ERROR', 'The request could not be completed.', fields={'full_name': ['This field is required.']})
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exists():
            return _api_error(
                'EMAIL_ALREADY_REGISTERED', 'An account with this email already exists.',
                fields={'email': ['An account with this email already exists.']},
                status_code=status.HTTP_409_CONFLICT,
            )
        first_name, _, last_name = full_name.partition(' ')
        candidate = email[:150]
        if user_model.objects.filter(username=candidate).exists():
            candidate = f'{email.split("@")[0][:120]}-{uuid4().hex[:12]}'
        user = user_model(username=candidate, email=email, first_name=first_name[:150], last_name=last_name[:150])
        try:
            password_validation.validate_password(password, user)
        except ValidationError as exc:
            return _api_error('VALIDATION_ERROR', 'The request could not be completed.', fields={'password': list(exc.messages)})
        user.set_password(password)
        try:
            with transaction.atomic():
                user.save()
                Customer.objects.create(user=user, name=full_name[:200], email=email)
        except IntegrityError:
            return _api_error(
                'EMAIL_ALREADY_REGISTERED', 'An account with this email already exists.',
                fields={'email': ['An account with this email already exists.']},
                status_code=status.HTTP_409_CONFLICT,
            )
        get_token(request._request)
        return _issue_tokens(user, bool(request.data.get('remember_me', False)))


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        raw_token = request.COOKIES.get('refresh_token')
        if not raw_token:
            return _api_error('SESSION_EXPIRED', 'Refresh session has expired. Sign in again.', status_code=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(raw_token)
            user = get_user_model().objects.get(pk=refresh['user_id'], is_active=True)
        except (TokenError, KeyError, get_user_model().DoesNotExist):
            return _api_error('SESSION_EXPIRED', 'Refresh session has expired. Sign in again.', status_code=status.HTTP_401_UNAUTHORIZED)
        if not constant_time_compare(refresh.get('password_stamp', ''), password_stamp(user)):
            return _api_error('PASSWORD_CHANGED', 'Your password changed. Sign in again.', status_code=status.HTTP_401_UNAUTHORIZED)
        remember_me = bool(refresh.get('remember_me', False))
        refresh.blacklist()
        replacement = RefreshToken.for_user(user)
        replacement['remember_me'] = remember_me
        replacement['password_stamp'] = password_stamp(user)
        response = Response({'access_token': str(replacement.access_token), 'user': _user_payload(user)})
        return _with_refresh_cookie(response, replacement, remember_me)


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        raw_token = request.COOKIES.get('refresh_token')
        if raw_token:
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass
        response = Response({'detail': 'Signed out.'})
        response.delete_cookie('refresh_token', path='/api/v1/auth/')
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))


    @transaction.atomic
    def patch(self, request):
        allowed = {'full_name', 'company', 'phone', 'billing_address'}
        unknown = set(request.data) - allowed
        if unknown:
            raise serializers.ValidationError({key: 'This field is not editable.' for key in unknown})
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        name = request.data.get('full_name')
        if name is not None:
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
                raise serializers.ValidationError({'full_name': 'Enter a name of 1 to 200 characters.'})
            first, _, last = name.strip().partition(' ')
            if len(first) > 150 or len(last) > 150:
                raise serializers.ValidationError({'full_name': 'Each name part must be at most 150 characters.'})
            user.first_name, user.last_name = first, last
            user.save(update_fields=['first_name', 'last_name'])
        customer = Customer.objects.select_for_update().filter(user=user).first()
        profile_data = {key: value for key, value in request.data.items() if key != 'full_name'}
        if name is not None:
            profile_data['name'] = name.strip()
        if customer:
            serializer = CustomerSerializer(customer, data=profile_data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        elif profile_data.keys() - {'name'}:
            raise serializers.ValidationError({'customer': 'This account has no customer profile.'})
        return Response(_user_payload(user))


class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'csrfToken': get_token(request._request)})
