
from django import forms
from django.forms.widgets import ClearableFileInput
from django.core.exceptions import ValidationError
from .models import Expediente
import os
import re


class MultipleFileInput(ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):

    widget = MultipleFileInput

    def clean(self, data, initial=None):

        if not data:
            if self.required:
                raise ValidationError(
                    "Debes seleccionar al menos un documento."
                )
            return []

        if not isinstance(data, (list, tuple)):
            data = [data]

        return [
            super(MultipleFileField, self).clean(archivo, initial)
            for archivo in data
        ]


def validar_archivos(archivos):
    for archivo in archivos:
        extension = os.path.splitext(archivo.name)[1].lower()

        if extension != ".pdf":
            raise ValidationError(
                f"El archivo {archivo.name} no está permitido. Solo se aceptan PDF."
            )

        if archivo.size > 10 * 1024 * 1024:
            raise ValidationError(
                f"El archivo {archivo.name} supera los 10 MB."
            )

    return archivos


class ExpedienteForm(forms.ModelForm):

    archivos = MultipleFileField(
        required=False,
        label="Adjuntar documentos"
    )

    class Meta:
        model = Expediente

        fields = [
            "rfc",
            "nombre",
            "direccion",
            "predial"
        ]

    def clean_rfc(self):

        rfc = self.cleaned_data["rfc"].strip().upper()

        patron = r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$"

        if not re.fullmatch(patron, rfc):
            raise ValidationError(
                "El formato del RFC no es válido."
            )

        return rfc

    def clean_predial(self):
        predial = self.cleaned_data["predial"].strip().upper()
        if len(predial) > 8:
            raise ValidationError(
                "La cuenta predial debe tener como máximo 8 caracteres."
            )

        expedientes_existentes = Expediente.objects.filter(
            predial__iexact=predial
        ).exclude(pk=self.instance.pk)
        if expedientes_existentes.exists():
            raise ValidationError(
                "Ya existe un expediente con esta cuenta predial."
            )

        return predial

    def clean_archivos(self):
        archivos = self.cleaned_data["archivos"]
        return validar_archivos(archivos)


class DocumentoForm(forms.Form):
    archivos = MultipleFileField(
        required=True,
        label="Selecciona uno o más documentos PDF"
    )

    def clean_archivos(self):
        return validar_archivos(self.cleaned_data["archivos"])
