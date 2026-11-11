import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import DocumentoForm, ExpedienteForm
from .models import Documento, Expediente


class ExpedienteFormTests(TestCase):
    def form_data(self, predial):
        return {
            "rfc": "ABC123456XYZ",
            "nombre": "Nombre de prueba",
            "direccion": "Calle de prueba",
            "predial": predial,
            "archivos": SimpleUploadedFile(
                "documento.pdf",
                b"contenido de prueba",
                content_type="application/pdf",
            ),
        }

    def test_predial_cannot_exceed_eight_characters(self):
        for value in ("123456789", "1234567890"):
            with self.subTest(predial=value):
                form = ExpedienteForm(
                    data=self.form_data(value),
                    files=self.form_data(value),
                )
                self.assertFalse(form.is_valid())
                self.assertIn("predial", form.errors)

    def test_predial_accepts_values_up_to_eight_characters(self):
        for value in ("1", "12345", "12345678"):
            with self.subTest(predial=value):
                data = self.form_data(value)
                form = ExpedienteForm(data=data, files=data)
                self.assertTrue(form.is_valid(), form.errors)

    def test_predial_must_be_unique(self):
        Expediente.objects.create(
            rfc="ABC123456XYZ",
            nombre="Expediente existente",
            direccion="Calle 1",
            predial="12345678",
        )
        data = self.form_data("12345678")
        form = ExpedienteForm(data=data, files=data)

        self.assertFalse(form.is_valid())
        self.assertIn("predial", form.errors)


class ExpedienteListTests(TestCase):
    def setUp(self):
        Expediente.objects.create(
            rfc="ABC123456XYZ",
            nombre="Expediente encontrado",
            direccion="Calle 1",
            predial="12345678",
        )
        Expediente.objects.create(
            rfc="DEF123456XYZ",
            nombre="Otro expediente",
            direccion="Calle 2",
            predial="87654321",
        )

    def test_search_returns_only_exact_rfc_case_insensitively(self):
        response = self.client.get(
            reverse("lista_expedientes"),
            {"rfc": "abc123456xyz"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Expediente encontrado")
        self.assertNotContains(response, "Otro expediente")
        self.assertEqual(len(response.context["expedientes"]), 1)

    def test_partial_rfc_does_not_return_multiple_records(self):
        response = self.client.get(reverse("lista_expedientes"), {"rfc": "ABC"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["expedientes"]), 0)
        self.assertContains(response, "Verifica el RFC e intenta nuevamente.")

    def test_list_paginates_twelve_records_and_shows_remaining_on_last_page(self):
        for index in range(25):
            Expediente.objects.create(
                rfc=f"XYZ{index:06d}ABC",
                nombre=f"Expediente {index}",
                direccion=f"Calle {index}",
                predial=f"{index:08d}",
            )

        first_page = self.client.get(reverse("lista_expedientes"))
        second_page = self.client.get(reverse("lista_expedientes"), {"page": 2})
        third_page = self.client.get(reverse("lista_expedientes"), {"page": 3})

        self.assertEqual(len(first_page.context["expedientes"]), 12)
        self.assertEqual(len(second_page.context["expedientes"]), 12)
        self.assertEqual(len(third_page.context["expedientes"]), 3)
        self.assertEqual(third_page.context["page_obj"].paginator.count, 27)

    def test_pagination_keeps_exact_rfc_filter(self):
        response = self.client.get(
            reverse("lista_expedientes"),
            {"rfc": "abc123456xyz", "page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["expedientes"]), 1)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(response.context["rfc"], "ABC123456XYZ")

    def test_list_shows_delete_button_for_each_expediente(self):
        response = self.client.get(reverse("lista_expedientes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("eliminar_expediente", args=["ABC123456XYZ"]),
        )
        self.assertContains(response, 'aria-label="Eliminar expediente ABC123456XYZ"')
        self.assertContains(response, "<span>Eliminar</span>", html=True)
        self.assertContains(response, "Esta acción no se puede deshacer.")

    def test_delete_endpoint_requires_post(self):
        response = self.client.get(
            reverse("eliminar_expediente", args=["ABC123456XYZ"])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Expediente.objects.filter(rfc="ABC123456XYZ").exists())

    def test_registration_shows_success_modal_before_list_redirect(self):
        data = {
            "rfc": "GHI123456XYZ",
            "nombre": "Nuevo expediente",
            "direccion": "Calle 3",
            "predial": "11223344",
            "archivos": SimpleUploadedFile(
                "documento.pdf",
                b"contenido de prueba",
                content_type="application/pdf",
            ),
        }
        response = self.client.post(
            reverse("registro"),
            data=data,
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], reverse("registro"))
        self.assertContains(response, "Expediente se guardó correctamente.")
        self.assertContains(response, 'role="alertdialog"')
        self.assertContains(response, reverse("lista_expedientes"))
        self.assertTrue(Expediente.objects.filter(rfc="GHI123456XYZ").exists())


class ExpedienteDocumentTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        override = override_settings(MEDIA_ROOT=self.media_directory.name)
        override.enable()
        self.addCleanup(override.disable)

        self.expediente = Expediente.objects.create(
            rfc="JKL123456XYZ",
            nombre="Expediente para documentos",
            direccion="Calle 4",
            predial="99887766",
        )

    def uploaded_pdf(self, name="documento.pdf"):
        return SimpleUploadedFile(
            name,
            b"contenido PDF de prueba",
            content_type="application/pdf",
        )

    def test_documents_are_kept_when_other_registration_fields_are_invalid(self):
        response = self.client.post(
            reverse("registro"),
            {
                "rfc": "MNO123456XYZ",
                "nombre": "",
                "direccion": "Calle 5",
                "predial": "11223344",
                "archivos": self.uploaded_pdf("conservar.pdf"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "conservar.pdf")
        self.assertContains(response, "Archivos conservados")

        response = self.client.post(
            reverse("registro"),
            {
                "rfc": "MNO123456XYZ",
                "nombre": "Nombre corregido",
                "direccion": "Calle 5",
                "predial": "11223344",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        expediente = Expediente.objects.get(rfc="MNO123456XYZ")
        self.assertEqual(expediente.documentos.count(), 1)
        self.assertTrue(expediente.documentos.first().archivo.name.endswith("conservar.pdf"))

    def test_detail_page_accepts_additional_documents(self):
        response = self.client.post(
            reverse("detalle_expediente", args=[self.expediente.rfc]),
            {"archivos": self.uploaded_pdf("adicional.pdf")},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.expediente.documentos.count(), 1)
        self.assertContains(response, "Los documentos se agregaron correctamente.")
        self.assertContains(response, "adicional.pdf")

    def test_delete_removes_expediente_and_attached_files(self):
        documento = Documento.objects.create(
            expediente=self.expediente,
            archivo=self.uploaded_pdf("adjunto.pdf"),
        )
        archivo_guardado = documento.archivo.name
        self.assertTrue(documento.archivo.storage.exists(archivo_guardado))

        response = self.client.post(
            reverse("eliminar_expediente", args=[self.expediente.rfc]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0],
            reverse("lista_expedientes"),
        )
        self.assertContains(response, "El expediente se eliminó correctamente.")
        self.assertFalse(Expediente.objects.filter(pk=self.expediente.pk).exists())
        self.assertFalse(Documento.objects.filter(pk=documento.pk).exists())
        self.assertFalse(documento.archivo.storage.exists(archivo_guardado))

    def test_detail_shows_link_to_update_general_data(self):
        response = self.client.get(
            reverse("detalle_expediente", args=[self.expediente.rfc])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("editar_expediente", args=[self.expediente.rfc]),
        )
        self.assertContains(response, "Actualizar datos")

    def test_general_data_can_be_updated(self):
        response = self.client.post(
            reverse("editar_expediente", args=[self.expediente.rfc]),
            {
                "rfc": "MNO123456XYZ",
                "nombre": "Nombre actualizado",
                "direccion": "Calle actualizada",
                "predial": "12344321",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0],
            reverse("detalle_expediente", args=["MNO123456XYZ"]),
        )
        self.assertContains(response, "Los datos del expediente se actualizaron correctamente.")
        self.expediente.refresh_from_db()
        self.assertEqual(self.expediente.rfc, "MNO123456XYZ")
        self.assertEqual(self.expediente.nombre, "Nombre actualizado")
        self.assertEqual(self.expediente.direccion, "Calle actualizada")
        self.assertEqual(self.expediente.predial, "12344321")

    def test_general_data_update_rejects_duplicate_predial(self):
        Expediente.objects.create(
            rfc="PQR123456XYZ",
            nombre="Otro expediente",
            direccion="Calle 5",
            predial="11223344",
        )

        response = self.client.post(
            reverse("editar_expediente", args=[self.expediente.rfc]),
            {
                "rfc": self.expediente.rfc,
                "nombre": "Nombre actualizado",
                "direccion": "Calle actualizada",
                "predial": "11223344",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un expediente con esta cuenta predial.")
        self.expediente.refresh_from_db()
        self.assertEqual(self.expediente.predial, "99887766")
