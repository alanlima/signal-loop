from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ValidatedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Use model.save() or membership services for validated updates.")

    def bulk_create(self, *args, **kwargs):
        raise TypeError("Bulk membership writes are not supported; use validated saves.")

    def bulk_update(self, *args, **kwargs):
        raise TypeError("Bulk membership writes are not supported; use validated saves.")

    def delete(self):
        raise TypeError("Use is_active=False; membership records are retained.")


class ValidatedModel(models.Model):
    objects = ValidatedQuerySet.as_manager()
    immutable_fields = ()

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(*self.immutable_fields).first()
            if original:
                for field in self.immutable_fields:
                    if original[field] != getattr(self, field):
                        raise ValidationError({field.removesuffix("_id"): "This association cannot change."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Use is_active=False; membership records are retained.")


class Role(models.TextChoices):
    MEMBER = "member", "Member"
    MANAGER = "manager", "Manager"


class Organisation(ValidatedModel):
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Project(ValidatedModel):
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="projects")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    immutable_fields = ("organisation_id",)

    def __str__(self):
        return self.name


class OrganisationMembership(ValidatedModel):
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organisation_memberships")
    role = models.CharField(max_length=7, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    immutable_fields = ("organisation_id", "user_id")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation", "user"], name="unique_organisation_member"),
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="valid_organisation_role"),
        ]


class ProjectMembership(ValidatedModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="memberships")
    organisation_membership = models.ForeignKey(OrganisationMembership, on_delete=models.PROTECT, related_name="project_memberships")
    role = models.CharField(max_length=7, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    immutable_fields = ("project_id", "organisation_membership_id")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "organisation_membership"], name="unique_project_member"),
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="valid_project_role"),
        ]

    def clean(self):
        super().clean()
        project_org = Project.objects.filter(pk=self.project_id).values_list("organisation_id", flat=True).first()
        member_org = OrganisationMembership.objects.filter(pk=self.organisation_membership_id).values_list("organisation_id", flat=True).first()
        if project_org is not None and member_org is not None and project_org != member_org:
            raise ValidationError({"organisation_membership": "Membership must belong to the project's organisation."})
