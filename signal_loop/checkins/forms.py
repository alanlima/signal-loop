from django import forms


def choices(values):
    return [("", "Choose an answer")] + [(value, value.replace("_", " ").capitalize()) for value in values]


class ReflectionText(forms.CharField):
    def to_python(self, value):
        return super().to_python(value).replace("\r\n", "\n").replace("\r", "\n")

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        # HTML maxlength counts UTF-16 units; the policy counts Unicode code points.
        attrs.pop("maxlength", None)
        return attrs


class PersonalForm(forms.Form):
    P1 = forms.ChoiceField(label="How is your energy this week?",
                          choices=choices(["low", "steady", "high", "prefer_not_to_say"]))
    P2 = forms.ChoiceField(label="How manageable is your workload this week?",
                          choices=choices(["manageable", "stretched", "overloaded", "prefer_not_to_say"]))
    P3 = ReflectionText(label="What went well for you this week?", required=False, max_length=240, strip=False,
                       widget=forms.Textarea(attrs={"rows": 3, "data-codepoint-limit": 240}),
                       help_text="Up to 240 characters. Avoid names, exact dates and details that could identify someone.")
    P4 = ReflectionText(label="What was difficult for you this week?", required=False, max_length=240, strip=False,
                       widget=forms.Textarea(attrs={"rows": 3, "data-codepoint-limit": 240}),
                       help_text="Up to 240 characters. Avoid names, exact dates and details that could identify someone.")
    P5 = ReflectionText(label="What support would help you next week?", required=False, max_length=240, strip=False,
                       widget=forms.Textarea(attrs={"rows": 3, "data-codepoint-limit": 240}),
                       help_text="Up to 240 characters. Avoid names, exact dates and details that could identify someone.")


class ProjectForm(forms.Form):
    J1 = forms.ChoiceField(choices=choices(["on_track", "at_risk", "blocked", "not_enough_context", "prefer_not_to_say"]))
    J2 = forms.ChoiceField(choices=choices(["manageable", "stretched", "overloaded", "not_enough_context", "prefer_not_to_say"]))
    J3 = ReflectionText(required=False, max_length=320, strip=False,
                       widget=forms.Textarea(attrs={"rows": 3, "data-codepoint-limit": 320}),
                       help_text="Up to 320 characters. Avoid names, exact dates and details that could identify someone.")

    def __init__(self, *args, project_name, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["J1"].label = f"How is delivery going in {project_name} this week?"
        self.fields["J2"].label = f"How manageable is the work in {project_name} this week?"
        self.fields["J3"].label = f"What should improve or continue in {project_name} next week?"
