from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from flux.bridge.models import IgnitionBridgeConfig


class IgnitionBridgeConfigForm(forms.Form):
    bridge_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(max_length=64)
    role = forms.ChoiceField(choices=IgnitionBridgeConfig.Role.choices)
    base_url = forms.URLField(widget=forms.URLInput(attrs={"autocomplete": "off"}))
    token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}, render_value=False),
    )
    clear_token = forms.BooleanField(required=False)

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def save(self) -> IgnitionBridgeConfig:
        bridge_id = self.cleaned_data.get("bridge_id")
        name = self.cleaned_data["name"]
        config = IgnitionBridgeConfig.objects.filter(id=bridge_id).first() if bridge_id else None
        config = config or IgnitionBridgeConfig.objects.filter(name=name).first()
        if config is None:
            config = IgnitionBridgeConfig(name=name)
        config.name = name
        config.role = self.cleaned_data["role"]
        config.base_url = self.cleaned_data["base_url"]
        token = self.cleaned_data.get("token", "")
        if self.cleaned_data.get("clear_token"):
            config.token = ""
        elif token:
            config.token = token
        config.last_test_ok = False
        config.last_test_message = "Connection has not been tested since the latest change."
        config.last_test_at = None
        config.save()
        return config


class InitialSuperuserForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        user.is_staff = True
        user.is_superuser = True
        if commit:
            user.save()
        return user
