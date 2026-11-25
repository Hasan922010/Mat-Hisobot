from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("preview-file/", views.preview_file, name="preview_file"),
    path("check-compatibility/", views.check_compatibility, name="check_compatibility"),
    path("batches/<int:pk>/", views.batch_detail, name="batch_detail"),
    path("batches/<int:pk>/progress/", views.batch_progress, name="batch_progress"),
    path("batches/<int:pk>/export/", views.export_excel, name="export_excel"),
    path("batches/<int:pk>/delete/", views.delete_batch, name="delete_batch"),
]
