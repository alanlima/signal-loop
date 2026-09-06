from django.db import migrations, models


def canonicalize(apps, schema_editor):
    section = apps.get_model("feedback", "FeedbackSection")
    for row in section.objects.using(schema_editor.connection.alias).all().iterator():
        answers = row.data
        data = {"source": str(row.pk), "delivery": answers["J1"], "workload": answers["J2"]}
        if "J3" in answers:
            data["note"] = answers["J3"]
        for question in ("F1", "F2"):
            if question in answers:
                data["follow_up"] = {"question": question, "answer": answers[question]}
        row.data = data
        row.schema = "feedback/1.0"
        row.provenance = {"producer": "feedback-store", "producer_version": "1.0", "input_refs": []}
        row.save(update_fields=["data", "schema", "provenance"])


def restore_intake(apps, schema_editor):
    section = apps.get_model("feedback", "FeedbackSection")
    for row in section.objects.using(schema_editor.connection.alias).all().iterator():
        data = row.data
        answers = {"J1": data["delivery"], "J2": data["workload"]}
        if "note" in data:
            answers["J3"] = data["note"]
        if "follow_up" in data:
            answers[data["follow_up"]["question"]] = data["follow_up"]["answer"]
        row.data = answers
        row.schema = "project-feedback/1.0"
        row.save(update_fields=["data", "schema"])


class Migration(migrations.Migration):
    dependencies = [("feedback", "0001_initial")]
    operations = [
        migrations.RenameField(model_name="feedbacksection", old_name="answers", new_name="data"),
        migrations.AddField(model_name="feedbacksection", name="provenance", field=models.JSONField(default=dict)),
        migrations.RunPython(canonicalize, restore_intake),
    ]
