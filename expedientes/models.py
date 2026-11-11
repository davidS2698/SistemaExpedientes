
from django.db import models
import os


def ruta_documento(instance, filename):
    rfc = instance.expediente.rfc
    return f"documentos/{rfc}/{filename}"


class Expediente(models.Model):

    rfc = models.CharField( max_length=13, unique=True)

    nombre = models.CharField(max_length=150)

    direccion = models.CharField(max_length=250)

    predial = models.CharField(max_length=50)

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.rfc


class Documento(models.Model):

    expediente = models.ForeignKey(
        Expediente,
        on_delete=models.CASCADE,
        related_name="documentos"
    )

    archivo = models.FileField(
        upload_to=ruta_documento
    )

    fecha_subida = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return os.path.basename(self.archivo.name)
