
from django.urls import path
from . import views


urlpatterns = [

    path(
        "",
        views.registrar_expediente,
        name="registro"
    ),

    path(
        "expedientes/",
        views.lista_expedientes,
        name="lista_expedientes"
    ),

    path(
        "expedientes/<str:rfc>/",
        views.detalle_expediente,
        name="detalle_expediente"
    ),

    path(
        "expedientes/<str:rfc>/editar/",
        views.editar_expediente,
        name="editar_expediente"
    ),

    path(
        "expedientes/<str:rfc>/eliminar/",
        views.eliminar_expediente,
        name="eliminar_expediente"
    ),

]
