from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import PermissionDenied

from signal_loop.authorization.permissions import Permission, has_permission
from .models import Organisation, OrganisationMembership, Project, ProjectMembership, Role


def administered_organisations(user):
    if not user.is_authenticated or not user.is_active:
        return []
    candidates = OrganisationMembership.objects.filter(
        user=user, role=Role.MANAGER, is_active=True, organisation__is_active=True,
    ).values_list("organisation_id", flat=True)
    return [pk for pk in candidates if has_permission(
        user, Permission.ADMINISTER_ORGANISATION, organisation_id=pk,
    )]


class OrganisationAdminLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not administered_organisations(user):
            raise self.get_invalid_login_error()


class OrganisationAdminSite(admin.AdminSite):
    site_header = "SignalLoop organisation administration"
    login_form = OrganisationAdminLoginForm

    def has_permission(self, request):
        return bool(administered_organisations(request.user))


site = OrganisationAdminSite(name="organisation_admin")


class ScopedAdmin(admin.ModelAdmin):
    actions = None
    list_display = ("__str__", "is_active")
    organisation_lookup = "organisation_id"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(**{
            f"{self.organisation_lookup}__in": administered_organisations(request.user),
        })

    def permitted(self, request, obj=None):
        if not administered_organisations(request.user):
            return False
        return obj is None or self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_module_permission(self, request):
        return self.permitted(request)

    def has_view_permission(self, request, obj=None):
        return self.permitted(request, obj)

    def has_add_permission(self, request):
        return self.permitted(request)

    def has_change_permission(self, request, obj=None):
        return self.permitted(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        scope = administered_organisations(request.user)
        lookups = {
            "organisation": {"pk__in": scope},
            "project": {"organisation_id__in": scope},
            "organisation_membership": {"organisation_id__in": scope},
            "user": {"organisation_memberships__organisation_id__in": scope},
        }
        if db_field.name in lookups:
            kwargs["queryset"] = db_field.remote_field.model.objects.filter(**lookups[db_field.name]).distinct()
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "organisation_membership":
            field.label_from_instance = lambda membership: f"{membership.user.username} ({membership.organisation.name})"
        return field

    def save_model(self, request, obj, form, change):
        # Form querysets reject tampering; recheck scope before writing as defense in depth.
        organisation_id = obj.project.organisation_id if isinstance(obj, ProjectMembership) else obj.organisation_id
        if not has_permission(request.user, Permission.ADMINISTER_ORGANISATION, organisation_id=organisation_id):
            raise PermissionDenied
        if change and not self.permitted(request, obj):
            raise PermissionDenied
        super().save_model(request, obj, form, change)


@admin.register(Project, site=site)
class ProjectAdmin(ScopedAdmin):
    fields = ("organisation", "name", "is_active")


@admin.register(OrganisationMembership, site=site)
class OrganisationMembershipAdmin(ScopedAdmin):
    fields = ("organisation", "user", "role", "is_active")
    list_display = ("user", "organisation", "role", "is_active")


@admin.register(ProjectMembership, site=site)
class ProjectMembershipAdmin(ScopedAdmin):
    organisation_lookup = "project__organisation_id"
    fields = ("project", "organisation_membership", "role", "is_active")
    list_display = ("project", "organisation_membership", "role", "is_active")


class ProvisionUserForm(UserCreationForm):
    organisation = forms.ModelChoiceField(queryset=Organisation.objects.none())

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)


@admin.register(get_user_model(), site=site)
class ProvisionUserAdmin(ScopedAdmin):
    organisation_lookup = "organisation_memberships__organisation_id"
    list_display = ("username",)

    def get_queryset(self, request):
        return super().get_queryset(request).distinct()

    def get_fields(self, request, obj=None):
        return ("username",) if obj else ("username", "organisation", "password1", "password2")

    def get_readonly_fields(self, request, obj=None):
        return ("username",) if obj else ()

    def has_change_permission(self, request, obj=None):
        # Shared account identity/password/global flags are not organisation-owned.
        return False

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            scope = administered_organisations(request.user)

            class ScopedProvisionForm(ProvisionUserForm):
                def __init__(self, *args, **form_kwargs):
                    super().__init__(*args, **form_kwargs)
                    self.fields["organisation"].queryset = Organisation.objects.filter(pk__in=scope)

            kwargs["form"] = ScopedProvisionForm
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        organisation = form.cleaned_data["organisation"]
        if change or not has_permission(request.user, Permission.ADMINISTER_ORGANISATION, organisation_id=organisation.pk):
            raise PermissionDenied
        obj.is_staff = False
        obj.is_superuser = False
        obj.is_active = True
        obj.save()
        # Django's admin changeform wraps save_model/save_related in one transaction.
        OrganisationMembership.objects.create(organisation=organisation, user=obj, role=Role.MEMBER)
