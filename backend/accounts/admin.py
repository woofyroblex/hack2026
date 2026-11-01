from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User


class AdminManagedUserAdmin(UserAdmin):
    """Keep staff and administrator account management with superusers."""

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class AdminManagedGroupAdmin(GroupAdmin):
    """Only administrators can grant or change permission groups."""

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, AdminManagedUserAdmin)
admin.site.register(Group, AdminManagedGroupAdmin)
