
import logging
import os
from uuid import uuid4

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.files import File
from django.core.paginator import Paginator
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.views.decorators.http import require_POST

from .forms import DocumentoForm, ExpedienteForm
from .models import Expediente, Documento


logger = logging.getLogger(__name__)
PENDING_DOCUMENTS_KEY = "expedientes_pending_documents"


def _pending_documents(request):
    return request.session.get(PENDING_DOCUMENTS_KEY, [])


def _stage_documents(request, archivos):
    pending = list(_pending_documents(request))
    for archivo in archivos:
        extension = os.path.splitext(archivo.name)[1].lower()
        path = default_storage.save(
            f"pending/expedientes/{uuid4().hex}{extension}",
            archivo,
        )
        pending.append({"path": path, "name": os.path.basename(archivo.name)})
    request.session[PENDING_DOCUMENTS_KEY] = pending
    return pending


def _delete_pending_documents(request):
    for documento in _pending_documents(request):
        try:
            default_storage.delete(documento["path"])
        except OSError:
            logger.warning(
                "No se pudo eliminar un documento temporal de expediente.",
                exc_info=True,
            )
    request.session.pop(PENDING_DOCUMENTS_KEY, None)


def registrar_expediente(request):
    if request.method == "POST":
        form = ExpedienteForm(request.POST, request.FILES)
        if form.is_valid():
            archivos = form.cleaned_data.get("archivos", [])
            pending = _pending_documents(request)
            missing_pending = [
                documento
                for documento in pending
                if not default_storage.exists(documento["path"])
            ]

            if missing_pending:
                form.add_error(
                    "archivos",
                    "No se encontraron algunos documentos guardados temporalmente. "
                    "Vuelve a adjuntarlos para continuar.",
                )
            elif not pending and not archivos:
                form.add_error(
                    "archivos",
                    "Debes seleccionar al menos un documento PDF.",
                )
            else:
                try:
                    with transaction.atomic():
                        expediente = form.save()

                        for documento in pending:
                            with default_storage.open(documento["path"], "rb") as archivo:
                                Documento.objects.create(
                                    expediente=expediente,
                                    archivo=File(archivo, name=documento["name"]),
                                )

                        for archivo in archivos:
                            Documento.objects.create(
                                expediente=expediente,
                                archivo=archivo,
                            )

                except IntegrityError:
                    logger.exception("No se pudo registrar el expediente por un dato duplicado.")
                    messages.error(
                        request,
                        "Ya existe un expediente con el RFC o la cuenta predial ingresados.",
                    )
                except OSError:
                    logger.exception("No se pudieron guardar los documentos del expediente.")
                    messages.error(
                        request,
                        "No se pudieron guardar los documentos. Intenta nuevamente.",
                    )
                else:
                    _delete_pending_documents(request)
                    messages.success(
                        request,
                        "Expediente se guardó correctamente."
                    )
                    return redirect("registro")

        if not form.is_valid():
            archivos_validos = form.cleaned_data.get("archivos", [])
            if archivos_validos:
                try:
                    _stage_documents(request, archivos_validos)
                except OSError:
                    logger.exception("No se pudieron conservar los documentos cargados.")
                    form.add_error(
                        "archivos",
                        "No se pudieron conservar los documentos cargados. Intenta adjuntarlos otra vez.",
                    )

        return render(
            request,
            "expedientes/registro.html",
            {
                "form": form,
                "pending_documents": _pending_documents(request),
            }
        )
    else:
        form = ExpedienteForm()

    return render(
        request,
        "expedientes/registro.html",
        {
            "form": form,
            "pending_documents": _pending_documents(request),
        }
    )


def lista_expedientes(request):
    rfc = request.GET.get("rfc", "").strip().upper()
    expedientes = Expediente.objects.all()
    if rfc:
        expedientes = expedientes.filter(rfc__iexact=rfc)
    expedientes = expedientes.order_by("-fecha_registro")
    page_obj = Paginator(expedientes, 12).get_page(request.GET.get("page"))

    return render(
        request,
        "expedientes/lista_expedientes.html",
        {"page_obj": page_obj, "expedientes": page_obj.object_list, "rfc": rfc}
    )


def detalle_expediente(request, rfc):
    expediente = get_object_or_404(
        Expediente.objects.prefetch_related("documentos"),
        rfc=rfc
    )

    if request.method == "POST":
        form = DocumentoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    for archivo in form.cleaned_data["archivos"]:
                        Documento.objects.create(
                            expediente=expediente,
                            archivo=archivo
                        )
            except OSError:
                logger.exception(
                    "No se pudieron agregar documentos al expediente %s.",
                    expediente.pk,
                )
                messages.error(
                    request,
                    "No se pudieron guardar los documentos. Intenta nuevamente."
                )
            else:
                messages.success(request, "Los documentos se agregaron correctamente.")
                return redirect("detalle_expediente", rfc=expediente.rfc)
    else:
        form = DocumentoForm()

    return render(
        request,
        "expedientes/detalle_expediente.html",
        {"expediente": expediente, "form": form}
    )


def editar_expediente(request, rfc):
    expediente = get_object_or_404(Expediente, rfc=rfc)

    if request.method == "POST":
        form = ExpedienteForm(request.POST, instance=expediente)
        if form.is_valid():
            try:
                with transaction.atomic():
                    expediente = form.save()
            except IntegrityError:
                logger.exception(
                    "No se pudieron actualizar los datos del expediente %s.",
                    expediente.pk,
                )
                messages.error(
                    request,
                    "Ya existe un expediente con el RFC o la cuenta predial ingresados.",
                )
            else:
                messages.success(request, "Los datos del expediente se actualizaron correctamente.")
                return redirect("detalle_expediente", rfc=expediente.rfc)
    else:
        form = ExpedienteForm(instance=expediente)

    return render(
        request,
        "expedientes/editar_expediente.html",
        {"expediente": expediente, "form": form}
    )


@require_POST
def eliminar_expediente(request, rfc):
    expediente = get_object_or_404(Expediente, rfc=rfc)
    archivos = list(
        expediente.documentos.values_list("archivo", flat=True)
    )

    with transaction.atomic():
        expediente.delete()

    archivos_no_eliminados = []
    for archivo in archivos:
        try:
            default_storage.delete(archivo)
        except OSError:
            logger.warning(
                "No se pudo eliminar el archivo %s del expediente %s.",
                archivo,
                rfc,
                exc_info=True,
            )
            archivos_no_eliminados.append(archivo)

    if archivos_no_eliminados:
        messages.warning(
            request,
            "El expediente se eliminó, pero no se pudieron borrar algunos documentos adjuntos.",
        )
    else:
        messages.success(request, "El expediente se eliminó correctamente.")

    return redirect("lista_expedientes")
